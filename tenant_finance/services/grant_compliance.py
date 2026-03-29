from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from django.db.models import Sum

from tenant_finance.models import (
    AccountCategory,
    GrantComplianceEvent,
    GrantComplianceRule,
    JournalEntry,
    JournalLine,
)
from tenant_grants.models import Grant


@dataclass
class GrantComplianceResult:
    status: str  # "ok", "warn", "block"
    message: str = ""


class GrantComplianceEngine:
    """
    Central engine for donor/grant-specific compliance checks.

    Current implementation focuses on:
    - Grant period validation
    - Eligible / ineligible account categories
    - Simple admin cost ceiling check at grant level
    - Flags for missing documents / procurement issues are left for callers to set
    """

    def __init__(self, tenant_db: str):
        self.tenant_db = tenant_db

    # ---- Rule selection -----------------------------------------------------

    def _get_applicable_rule(self, grant: Grant, entry_date: date) -> Optional[GrantComplianceRule]:
        qs = (
            GrantComplianceRule.objects.using(self.tenant_db)
            .filter(status=GrantComplianceRule.Status.ACTIVE)
            .filter(effective_from__lte=entry_date, effective_to__gte=entry_date)
        )

        # Prefer grant-specific rule, then donor-wide rules.
        rule = qs.filter(grant=grant).order_by("-effective_from").first()
        if rule:
            return rule
        if grant.donor_id:
            return qs.filter(donor_id=grant.donor_id, grant__isnull=True).order_by("-effective_from").first()
        return None

    # ---- Core checks --------------------------------------------------------

    def check_entry(
        self,
        entry: JournalEntry,
        *,
        has_attachments: bool = True,
        passes_procurement: bool = True,
    ) -> GrantComplianceResult:
        """
        Run grant compliance checks for a journal entry.

        Callers can pass lightweight context flags:
        - has_attachments: whether required supporting docs are attached
        - passes_procurement: whether procurement thresholds and approvals passed
        """
        if not entry.grant_id:
            return GrantComplianceResult(status="ok")

        grant: Grant = entry.grant
        entry_date = entry.entry_date

        rule = self._get_applicable_rule(grant, entry_date)
        if not rule:
            return GrantComplianceResult(status="ok")

        # 1. Grant period check
        if (
            grant.start_date
            and grant.end_date
            and not rule.allow_posting_outside_grant_period
            and (entry_date < grant.start_date or entry_date > grant.end_date)
        ):
            status = "warn" if rule.mode == GrantComplianceRule.Mode.WARN else "block"
            return GrantComplianceResult(
                status=status,
                message=f"Grant compliance: entry date {entry_date} is outside grant period "
                f"{grant.start_date} – {grant.end_date}.",
            )

        # 2. Category eligibility
        account_categories = (
            AccountCategory.objects.using(self.tenant_db)
            .filter(accounts__journalline__entry=entry)
            .distinct()
        )

        allowed_ids = set(rule.allowed_account_categories.values_list("id", flat=True))
        disallowed_ids = set(rule.disallowed_account_categories.values_list("id", flat=True))
        for cat in account_categories:
            if disallowed_ids and cat.id in disallowed_ids:
                status = "warn" if rule.mode == GrantComplianceRule.Mode.WARN else "block"
                return GrantComplianceResult(
                    status=status,
                    message=f"Grant compliance: account category {cat.code} is disallowed for this grant/donor.",
                )
        if allowed_ids and any(cat.id not in allowed_ids for cat in account_categories):
            status = "warn" if rule.mode == GrantComplianceRule.Mode.WARN else "block"
            return GrantComplianceResult(
                status=status,
                message="Grant compliance: one or more expense categories are not allowed by donor rules.",
            )

        # 3. Simple admin cost ceiling (if configured)
        if rule.maximum_admin_cost_percent and rule.maximum_admin_cost_percent > 0:
            admin_cats = AccountCategory.objects.using(self.tenant_db).filter(
                id__in=rule.allowed_account_categories.values_list("id", flat=True),
                name__icontains="admin",
            )
            admin_ids = list(admin_cats.values_list("id", flat=True))

            total_expense = (
                JournalLine.objects.using(self.tenant_db)
                .filter(entry__grant_id=grant.id)
                .aggregate(t=Sum("debit") - Sum("credit"))
                .get("t")
                or Decimal("0")
            )
            admin_expense = (
                JournalLine.objects.using(self.tenant_db)
                .filter(entry__grant_id=grant.id, account__category_id__in=admin_ids)
                .aggregate(t=Sum("debit") - Sum("credit"))
                .get("t")
                or Decimal("0")
            )
            projected_total = total_expense  # current implementation only looks at history

            if projected_total > 0:
                admin_ratio = admin_expense / projected_total * Decimal("100")
                if admin_ratio > rule.maximum_admin_cost_percent:
                    status = "warn" if rule.mode == GrantComplianceRule.Mode.WARN else "block"
                    return GrantComplianceResult(
                        status=status,
                        message=(
                            f"Grant compliance: admin costs {admin_ratio:.2f}% exceed ceiling "
                            f"{rule.maximum_admin_cost_percent:.2f}% for this grant/donor."
                        ),
                    )

        # 4. Supporting documents are optional for posting; never block on missing attachments.
        if rule.require_attachments and not has_attachments:
            return GrantComplianceResult(
                status="warn",
                message="Grant compliance: supporting documents are recommended for this grant/donor.",
            )
        if rule.require_procurement_compliance and not passes_procurement:
            status = "warn" if rule.mode == GrantComplianceRule.Mode.WARN else "block"
            return GrantComplianceResult(
                status=status,
                message="Grant compliance: procurement thresholds or approvals not satisfied.",
            )

        return GrantComplianceResult(status="ok")

    # ---- Logging ------------------------------------------------------------

    def log_event(
        self,
        *,
        entry: JournalEntry,
        rule: Optional[GrantComplianceRule],
        result: GrantComplianceResult,
        missing_documents: bool = False,
        procurement_issue: bool = False,
    ) -> None:
        GrantComplianceEvent.objects.using(self.tenant_db).create(
            event_type=(
                GrantComplianceEvent.EventType.BLOCK
                if result.status == "block"
                else GrantComplianceEvent.EventType.WARN
            ),
            rule=rule,
            entry=entry,
            donor=getattr(entry.grant, "donor", None) if entry.grant_id else None,
            grant=entry.grant if entry.grant_id else None,
            message=result.message,
            missing_documents=missing_documents,
            admin_ceiling_breach="admin costs" in (result.message or "").lower(),
            ineligible_category="category" in (result.message or "").lower(),
            outside_grant_period="outside grant period" in (result.message or "").lower(),
            procurement_issue=procurement_issue,
        )

