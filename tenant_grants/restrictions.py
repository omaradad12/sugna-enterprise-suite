"""
Donor restriction evaluation for journals, budgets, and procurement.

Callers should use evaluate_journal_post_restrictions() before posting a journal
that is tied to a grant. Extend evaluate_procurement_restrictions() for PR flows.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db.models import Q
from django.utils import timezone

if TYPE_CHECKING:
    from tenant_finance.models import JournalEntry

MANDATORY = "mandatory"
RECOMMENDED = "recommended"
INFORMATIONAL = "informational"


@dataclass
class RestrictionViolation:
    restriction_id: int
    restriction_code: str
    message: str
    compliance_level: str
    blocks_posting: bool
    requires_override: bool


def sync_donor_restriction_expiry(using: str) -> None:
    """Mark active restrictions as expired when effective_end < today."""
    from tenant_grants.models import DonorRestriction

    today = timezone.now().date()
    DonorRestriction.objects.using(using).filter(
        status=DonorRestriction.Status.ACTIVE,
        effective_end__isnull=False,
        effective_end__lt=today,
    ).update(status=DonorRestriction.Status.EXPIRED)


def applicable_restrictions_qs(
    *,
    using: str,
    donor_id: int,
    grant_id: int | None = None,
    project_id: int | None = None,
    funding_source_id: int | None = None,
    as_of=None,
):
    """
    Active restrictions that match donor and optional scope (grant/project/funding source).
    """
    from tenant_grants.models import DonorRestriction

    if as_of is None:
        as_of = timezone.now().date()
    sync_donor_restriction_expiry(using)

    qs = (
        DonorRestriction.objects.using(using)
        .filter(donor_id=donor_id)
        .filter(status=DonorRestriction.Status.ACTIVE)
    )
    qs = qs.filter(
        Q(effective_start__isnull=True) | Q(effective_start__lte=as_of)
    ).filter(Q(effective_end__isnull=True) | Q(effective_end__gte=as_of))

    scope_q = Q(applies_scope=DonorRestriction.AppliesScope.DONOR_WIDE)
    if funding_source_id:
        scope_q |= Q(
            applies_scope=DonorRestriction.AppliesScope.FUNDING_SOURCE,
            funding_source_id=funding_source_id,
        )
    if grant_id:
        scope_q |= Q(applies_scope=DonorRestriction.AppliesScope.GRANT, grant_id=grant_id)
        scope_q |= Q(grant_id=grant_id)
    if project_id:
        scope_q |= Q(
            applies_scope=DonorRestriction.AppliesScope.PROJECT, project_id=project_id
        )
        scope_q |= Q(project_id=project_id)
    return qs.filter(scope_q)


def _entry_expense_total(entry: JournalEntry, using: str) -> Decimal:
    from django.db.models import Sum
    from tenant_finance.models import ChartAccount

    agg = (
        entry.lines.using(using)
        .filter(account__type=ChartAccount.Type.EXPENSE)
        .aggregate(s=Sum("debit"))
    )
    return Decimal(str(agg.get("s") or 0))


def evaluate_journal_post_restrictions(
    entry: JournalEntry,
    using: str,
    *,
    has_override_permission: bool = False,
) -> list[RestrictionViolation]:
    """
    Check donor restrictions for a journal entry about to be posted.
    Mandatory violations return blocks_posting=True unless user has override and restriction allows it.
    """
    from tenant_grants.models import DonorRestriction

    if not entry.grant_id:
        return []

    from tenant_grants.models import Grant

    grant = Grant.objects.using(using).filter(pk=entry.grant_id).select_related("donor").first()
    if not grant or not grant.donor_id:
        return []

    funding_source_id = getattr(grant, "funding_source_id", None)
    project_id = getattr(grant, "project_id", None)

    qs = applicable_restrictions_qs(
        using=using,
        donor_id=grant.donor_id,
        grant_id=grant.pk,
        project_id=project_id,
        funding_source_id=funding_source_id,
    )
    restrictions = list(qs.select_related("account_category"))

    expense_total = _entry_expense_total(entry, using)
    violations: list[RestrictionViolation] = []

    for r in restrictions:
        if r.enforce_expense_eligibility and r.max_expense_per_transaction is not None:
            if expense_total > r.max_expense_per_transaction:
                msg = (
                    f"Donor restriction {r.restriction_code}: expense total {expense_total} exceeds "
                    f"maximum {r.max_expense_per_transaction} per transaction."
                )
                blocks = r.compliance_level == DonorRestriction.ComplianceLevel.MANDATORY
                if r.compliance_level != DonorRestriction.ComplianceLevel.MANDATORY:
                    blocks = False
                if blocks and r.require_approval_override and has_override_permission:
                    blocks = False
                violations.append(
                    RestrictionViolation(
                        restriction_id=r.pk,
                        restriction_code=r.restriction_code or "",
                        message=msg,
                        compliance_level=r.compliance_level,
                        blocks_posting=blocks,
                        requires_override=r.require_approval_override,
                    )
                )

        if r.enforce_expense_eligibility and r.account_category_id:
            from tenant_finance.models import ChartAccount

            bad_lines = (
                entry.lines.using(using)
                .filter(account__type=ChartAccount.Type.EXPENSE)
                .exclude(account__category_id=r.account_category_id)
            )
            if bad_lines.exists():
                msg = (
                    f"Donor restriction {r.restriction_code}: journal uses expense account(s) outside "
                    f"allowed category '{r.account_category.name}'."
                )
                blocks = r.compliance_level == DonorRestriction.ComplianceLevel.MANDATORY
                if r.compliance_level != DonorRestriction.ComplianceLevel.MANDATORY:
                    blocks = False
                if blocks and r.require_approval_override and has_override_permission:
                    blocks = False
                violations.append(
                    RestrictionViolation(
                        restriction_id=r.pk,
                        restriction_code=r.restriction_code or "",
                        message=msg,
                        compliance_level=r.compliance_level,
                        blocks_posting=blocks,
                        requires_override=r.require_approval_override,
                    )
                )

    return violations


def evaluate_procurement_restrictions(
    *,
    using: str,
    donor_id: int,
    grant_id: int | None,
    estimated_amount: Decimal | None,
    project_id: int | None = None,
    funding_source_id: int | None = None,
    has_override_permission: bool = False,
) -> list[RestrictionViolation]:
    """PR creation: procurement threshold / method enforcement (extend as needed)."""
    from tenant_grants.models import DonorRestriction

    qs = applicable_restrictions_qs(
        using=using,
        donor_id=donor_id,
        grant_id=grant_id,
        project_id=project_id,
        funding_source_id=funding_source_id,
    )
    out: list[RestrictionViolation] = []
    for r in qs:
        if not r.enforce_procurement_validation:
            continue
        if r.max_procurement_threshold is not None and estimated_amount is not None:
            if estimated_amount > r.max_procurement_threshold:
                msg = (
                    f"Donor restriction {r.restriction_code}: amount exceeds procurement threshold "
                    f"{r.max_procurement_threshold}."
                )
                blocks = r.compliance_level == DonorRestriction.ComplianceLevel.MANDATORY
                if r.compliance_level != DonorRestriction.ComplianceLevel.MANDATORY:
                    blocks = False
                if blocks and r.require_approval_override and has_override_permission:
                    blocks = False
                out.append(
                    RestrictionViolation(
                        restriction_id=r.pk,
                        restriction_code=r.restriction_code or "",
                        message=msg,
                        compliance_level=r.compliance_level,
                        blocks_posting=blocks,
                        requires_override=r.require_approval_override,
                    )
                )
    return out
