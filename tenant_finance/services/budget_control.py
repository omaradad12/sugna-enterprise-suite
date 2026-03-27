from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from django.db.models import Sum

from tenant_finance.models import (
    BudgetControlRule,
    BudgetEvent,
    BudgetOverrideRequest,
    ChartAccount,
    JournalEntry,
    JournalLine,
    get_grant_posted_expense_total,
)
from tenant_grants.models import BudgetLine, Grant


@dataclass
class BudgetCheckResult:
    status: str  # "ok", "warn", "critical", "block", "no_budget"
    message: str = ""
    utilization_percent: Optional[Decimal] = None
    over_amount: Optional[Decimal] = None
    details: dict | None = None


class BudgetControlEngine:
    """
    Central place for grant/project budget validation.

    Budget validation engine:
    - Budget line level enforcement using BudgetLine.account (preferred)
    - Available budget = budget - actuals - optionally commitments
    - Threshold bands: warn / critical / block
    - Override requests with approval & audit logging
    """

    def __init__(self, tenant_db: str):
        self.tenant_db = tenant_db

    # ---- Rules -------------------------------------------------------------

    def _get_rules(self) -> BudgetControlRule:
        rule = (
            BudgetControlRule.objects.using(self.tenant_db)
            .filter(is_active=True)
            .order_by("id")
            .first()
        )
        if not rule:
            rule = BudgetControlRule(
                name="Default budget control",
                warn_at_percent=Decimal("80"),
                critical_at_percent=Decimal("90"),
                block_at_percent=Decimal("100"),
            )
        return rule

    def _override_role_set(self, rule: BudgetControlRule) -> set[str]:
        raw = (rule.override_roles or "").strip()
        if not raw:
            return set()
        return {r.strip().lower() for r in raw.split(",") if r.strip()}

    def _user_has_override_role(self, user, rule: BudgetControlRule) -> bool:
        if not user or not rule.allow_override:
            return False
        # Best-effort: match by tenant role name (if present) or user's role_name field if exists.
        role_name = (getattr(user, "role_name", "") or "").strip().lower()
        if role_name and role_name in self._override_role_set(rule):
            return True
        # Some deployments expose a list of roles on tenant_user
        roles = getattr(user, "roles", None)
        if roles:
            try:
                for r in roles:
                    nm = (getattr(r, "name", "") or str(r) or "").strip().lower()
                    if nm and nm in self._override_role_set(rule):
                        return True
            except Exception:
                pass
        return False

    def _get_commitments_by_budget_line(self, grant: Grant) -> dict[str, Decimal]:
        """
        Commitments are sourced from PRs (Purchase Requisitions) not in terminal states.
        They are grouped by PR line 'budget_line' text (should match BudgetLine.budget_line_code).
        """
        from tenant_grants.models import PurchaseRequisition

        qs = PurchaseRequisition.objects.using(self.tenant_db).filter(grant=grant).exclude(
            status__in=[
                PurchaseRequisition.Status.REJECTED,
                PurchaseRequisition.Status.CANCELLED,
                PurchaseRequisition.Status.FULFILLED,
            ]
        )

        totals: dict[str, Decimal] = {}
        for pr in qs.prefetch_related("lines"):
            # Prefer lines (multi-line PR); else fallback to header budget_line
            if pr.lines.exists():
                for line in pr.lines.all():
                    key = (line.budget_line or "").strip()
                    if not key:
                        continue
                    totals[key] = totals.get(key, Decimal("0")) + (line.estimated_total_cost or Decimal("0"))
            else:
                key = (pr.budget_line or "").strip()
                if not key:
                    continue
                totals[key] = totals.get(key, Decimal("0")) + (pr.effective_total() or Decimal("0"))
        return totals

    def _budget_lines_for_grant(self, grant: Grant) -> list[BudgetLine]:
        return list(
            BudgetLine.objects.using(self.tenant_db)
            .select_related("account")
            .filter(grant=grant)
            .order_by("id")
        )

    def _actuals_by_account_for_grant(self, grant: Grant) -> dict[int, Decimal]:
        rows = (
            JournalLine.objects.using(self.tenant_db)
            .filter(
                entry__grant_id=grant.id,
                entry__status=JournalEntry.Status.POSTED,
                account__type=ChartAccount.Type.EXPENSE,
            )
            .values("account_id")
            .annotate(total=Sum("debit") - Sum("credit"))
        )
        return {r["account_id"]: (r["total"] or Decimal("0")) for r in rows}

    def _entry_expense_by_account(self, entry: JournalEntry) -> dict[int, Decimal]:
        rows = (
            JournalLine.objects.using(self.tenant_db)
            .filter(entry=entry, account__type=ChartAccount.Type.EXPENSE)
            .values("account_id")
            .annotate(total=Sum("debit") - Sum("credit"))
        )
        return {r["account_id"]: (r["total"] or Decimal("0")) for r in rows}

    # ---- Core check --------------------------------------------------------

    def check_entry(self, entry: JournalEntry) -> BudgetCheckResult:
        """
        Validate a journal entry that has a grant set.
        Aggregates expense impacts and checks against budget lines for the grant.
        """
        if not entry.grant_id:
            return BudgetCheckResult(status="ok")

        grant: Grant = entry.grant

        rules = self._get_rules()

        budget_lines = self._budget_lines_for_grant(grant)
        if not budget_lines:
            return BudgetCheckResult(
                status="no_budget",
                message=f"No approved budget defined for grant {grant.code}.",
            )

        actuals_by_account = self._actuals_by_account_for_grant(grant)
        entry_by_account = self._entry_expense_by_account(entry)
        commitments_by_category = (
            self._get_commitments_by_budget_line(grant) if rules.include_commitments else {}
        )

        worst = BudgetCheckResult(status="ok", details={})
        worst_rank = {"ok": 0, "warn": 1, "critical": 2, "block": 3, "no_budget": 0}

        details = {
            "grant": grant.code,
            "include_commitments": bool(rules.include_commitments),
            "lines": [],
        }

        for bl in budget_lines:
            budget_amt = bl.amount or Decimal("0")
            acct_id = bl.account_id
            line_code = (getattr(bl, "budget_line_code", "") or "").strip()
            line_name = (bl.category or "").strip()
            if not acct_id:
                # Can't enforce line-level without account coding; skip but record.
                details["lines"].append(
                    {
                        "budget_line_id": bl.id,
                        "budget_line_code": line_code,
                        "category": bl.category,
                        "budget": str(budget_amt),
                        "note": "No account mapped on budget line; skipped.",
                    }
                )
                continue

            actual = actuals_by_account.get(acct_id, Decimal("0"))
            new = entry_by_account.get(acct_id, Decimal("0"))
            commit = commitments_by_category.get(line_code, Decimal("0"))
            projected = actual + new + (commit if rules.include_commitments else Decimal("0"))

            util = (projected / budget_amt * Decimal("100")) if budget_amt > 0 else None
            over = projected - budget_amt if budget_amt > 0 and projected > budget_amt else Decimal("0")

            line_status = "ok"
            if budget_amt <= 0 and new > 0:
                line_status = "block"
                msg = f"Budget control: no budget amount for line '{line_code or line_name}' but entry posts {new}."
            elif util is not None:
                if util >= rules.block_at_percent:
                    line_status = "block"
                    msg = (
                        f"Budget line '{line_code or line_name}' will exceed budget {budget_amt} "
                        f"(projected {projected}, utilization {util:.2f}%)."
                    )
                elif util >= rules.critical_at_percent:
                    line_status = "critical"
                    msg = (
                        f"Budget line '{line_code or line_name}' will reach critical utilization {util:.2f}% "
                        f"of budget {budget_amt} (projected {projected})."
                    )
                elif util >= rules.warn_at_percent:
                    line_status = "warn"
                    msg = (
                        f"Budget line '{line_code or line_name}' will reach warning utilization {util:.2f}% "
                        f"of budget {budget_amt} (projected {projected})."
                    )
                else:
                    msg = ""
            else:
                msg = ""

            details["lines"].append(
                {
                    "budget_line_id": bl.id,
                    "budget_line_code": line_code,
                    "category": bl.category,
                    "account_id": acct_id,
                    "budget": str(budget_amt),
                    "actual": str(actual),
                    "commitments": str(commit),
                    "new": str(new),
                    "projected": str(projected),
                    "utilization_percent": str(util) if util is not None else None,
                    "status": line_status,
                    "over_amount": str(over),
                }
            )

            if worst_rank[line_status] > worst_rank[worst.status]:
                worst = BudgetCheckResult(
                    status=line_status,
                    message=msg,
                    utilization_percent=util if util is not None else None,
                    over_amount=over if over else None,
                    details=details,
                )

        worst.details = details
        return worst

    # ---- Audit logging -----------------------------------------------------

    def log_event(
        self,
        *,
        entry: JournalEntry,
        result: BudgetCheckResult,
        event_type: BudgetEvent.EventType,
        user,
        override_reason: str = "",
    ) -> None:
        BudgetEvent.objects.using(self.tenant_db).create(
            event_type=event_type,
            entry=entry,
            grant=entry.grant,
            project=getattr(entry.grant, "project", None) if entry.grant_id else None,
            budget_line_code="",
            account_code="",
            utilization_percent=result.utilization_percent,
            over_amount=result.over_amount,
            message=result.message,
            override_reason=override_reason,
            user=user,
        )

    # ---- Override workflow -------------------------------------------------

    def get_approved_override_for_entry(self, entry: JournalEntry) -> Optional[BudgetOverrideRequest]:
        return (
            BudgetOverrideRequest.objects.using(self.tenant_db)
            .filter(entry=entry, status=BudgetOverrideRequest.Status.APPROVED)
            .order_by("-requested_at")
            .first()
        )

    def request_override(
        self,
        *,
        entry: JournalEntry,
        user,
        reason: str,
        check_result: BudgetCheckResult,
    ) -> BudgetOverrideRequest:
        rule = self._get_rules()
        if not rule.allow_override:
            raise ValueError("Budget overrides are not enabled.")
        if not self._user_has_override_role(user, rule):
            raise ValueError("You are not authorized to request a budget override.")
        if not (reason or "").strip():
            raise ValueError("Override reason is required.")
        req = BudgetOverrideRequest.objects.using(self.tenant_db).create(
            entry=entry,
            rule=rule if rule and rule.pk else None,
            status=BudgetOverrideRequest.Status.PENDING,
            requested_by=user,
            reason=reason.strip(),
            check_snapshot=check_result.details or {},
        )
        return req

