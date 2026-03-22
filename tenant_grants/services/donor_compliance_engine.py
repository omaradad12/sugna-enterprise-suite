"""
Donor restriction compliance vs posted grant expenses (period-scoped).

Maps existing DonorRestriction fields:
  restriction_code → "code"
  restriction_type → "type"
  max_budget_percentage → percent cap of award(s)
  max_expense_per_transaction → per-line debit cap
  effective_start / effective_end → date window
  compliance_level → influences warning vs breach strictness (recommended → softer)
  status → must be active to evaluate as enforceable
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from django.db.models import Q, Sum

COMPLIANT = "compliant"
WARNING = "warning"
BREACH = "breach"
NOT_APPLICABLE = "not_applicable"


@dataclass
class ComplianceResult:
    code: str
    label: str
    css: str  # green | yellow | red | gray
    explanation: str
    grant_expense: Decimal
    allowed_budget: Decimal | None
    utilization_pct: Decimal | None
    variance: Decimal | None  # spend - allowed (negative = headroom)
    max_line_in_period: Decimal | None


def _money(x) -> Decimal:
    if x is None:
        return Decimal("0")
    return Decimal(str(x))


def restriction_overlaps_period(
    restriction: Any,
    period_start: date,
    period_end: date,
) -> bool:
    if restriction.effective_start and restriction.effective_start > period_end:
        return False
    if restriction.effective_end and restriction.effective_end < period_start:
        return False
    return True


def grant_ids_for_restriction(restriction: Any, tenant_db: str) -> list[int]:
    from tenant_grants.models import DonorRestriction, Grant

    if restriction.grant_id:
        return [restriction.grant_id]
    if restriction.project_id:
        return list(
            Grant.objects.using(tenant_db)
            .filter(project_id=restriction.project_id, status=Grant.Status.ACTIVE)
            .values_list("id", flat=True)
        )
    if restriction.applies_scope == DonorRestriction.AppliesScope.DONOR_WIDE:
        return list(
            Grant.objects.using(tenant_db)
            .filter(donor_id=restriction.donor_id, status=Grant.Status.ACTIVE)
            .values_list("id", flat=True)
        )
    if restriction.applies_scope == DonorRestriction.AppliesScope.FUNDING_SOURCE and restriction.funding_source_id:
        return list(
            Grant.objects.using(tenant_db)
            .filter(donor_id=restriction.donor_id, status=Grant.Status.ACTIVE)
            .values_list("id", flat=True)
        )
    return []


def award_total_for_grants(tenant_db: str, grant_ids: list[int]) -> Decimal:
    from tenant_grants.models import Grant

    if not grant_ids:
        return Decimal("0")
    total = (
        Grant.objects.using(tenant_db).filter(pk__in=grant_ids).aggregate(s=Sum("award_amount")).get("s")
        or 0
    )
    return _money(total)


def posted_grant_expense_in_period(
    tenant_db: str,
    grant_ids: list[int],
    period_start: date,
    period_end: date,
) -> tuple[Decimal, Decimal]:
    """
    Sum posted expense debits for grants in period; also return max single expense debit on a line.
    """
    from tenant_finance.models import ChartAccount, JournalEntry, JournalLine

    if not grant_ids:
        return Decimal("0"), Decimal("0")

    base = (
        JournalLine.objects.using(tenant_db)
        .filter(
            account__type=ChartAccount.Type.EXPENSE,
            entry__status=JournalEntry.Status.POSTED,
            entry__entry_date__gte=period_start,
            entry__entry_date__lte=period_end,
        )
        .filter(Q(entry__grant_id__in=grant_ids) | Q(grant_id__in=grant_ids))
    )
    from django.db.models import Max

    total = base.aggregate(s=Sum("debit")).get("s") or 0
    max_debit = base.aggregate(m=Max("debit")).get("m") or 0
    return _money(total), _money(max_debit)


def related_expense_lines(
    tenant_db: str,
    grant_ids: list[int],
    period_start: date,
    period_end: date,
    limit: int = 150,
):
    from tenant_finance.models import ChartAccount, JournalEntry, JournalLine

    if not grant_ids:
        return JournalLine.objects.none()

    return (
        JournalLine.objects.using(tenant_db)
        .filter(
            account__type=ChartAccount.Type.EXPENSE,
            entry__status=JournalEntry.Status.POSTED,
            entry__entry_date__gte=period_start,
            entry__entry_date__lte=period_end,
        )
        .filter(Q(entry__grant_id__in=grant_ids) | Q(grant_id__in=grant_ids))
        .filter(debit__gt=0)
        .select_related("entry", "account", "entry__grant")
        .order_by("-entry__entry_date", "-id")[:limit]
    )


def _label(code: str) -> str:
    return {
        COMPLIANT: "Compliant",
        WARNING: "Warning",
        BREACH: "Breach",
        NOT_APPLICABLE: "Not applicable",
    }.get(code, code)


def _css(code: str) -> str:
    return {
        COMPLIANT: "green",
        WARNING: "yellow",
        BREACH: "red",
        NOT_APPLICABLE: "gray",
    }.get(code, "gray")


def evaluate_restriction(
    restriction: Any,
    *,
    tenant_db: str,
    period_start: date,
    period_end: date,
) -> ComplianceResult:
    from tenant_grants.models import DonorRestriction

    if restriction.status != DonorRestriction.Status.ACTIVE:
        return ComplianceResult(
            code=NOT_APPLICABLE,
            label=_label(NOT_APPLICABLE),
            css=_css(NOT_APPLICABLE),
            explanation="Restriction is not active; spend rules are not evaluated.",
            grant_expense=Decimal("0"),
            allowed_budget=None,
            utilization_pct=None,
            variance=None,
            max_line_in_period=None,
        )

    if not restriction_overlaps_period(restriction, period_start, period_end):
        return ComplianceResult(
            code=NOT_APPLICABLE,
            label=_label(NOT_APPLICABLE),
            css=_css(NOT_APPLICABLE),
            explanation="Effective dates do not overlap the selected reporting period.",
            grant_expense=Decimal("0"),
            allowed_budget=None,
            utilization_pct=None,
            variance=None,
            max_line_in_period=None,
        )

    gids = grant_ids_for_restriction(restriction, tenant_db)
    spend, max_line = posted_grant_expense_in_period(tenant_db, gids, period_start, period_end)
    award = award_total_for_grants(tenant_db, gids)

    if not gids:
        return ComplianceResult(
            code=NOT_APPLICABLE,
            label=_label(NOT_APPLICABLE),
            css=_css(NOT_APPLICABLE),
            explanation="No grant scope linked (add a grant or donor-wide grants) to evaluate posted expenses.",
            grant_expense=spend,
            allowed_budget=None,
            utilization_pct=None,
            variance=None,
            max_line_in_period=max_line if max_line > 0 else None,
        )

    # Reporting-only restrictions: no spend test
    if restriction.category == DonorRestriction.Category.REPORTING or str(
        restriction.restriction_type or ""
    ).startswith("rep_"):
        return ComplianceResult(
            code=NOT_APPLICABLE,
            label=_label(NOT_APPLICABLE),
            css=_css(NOT_APPLICABLE),
            explanation="Reporting restriction — compliance is not derived from posted expenses.",
            grant_expense=spend,
            allowed_budget=None,
            utilization_pct=(spend / award * Decimal("100")) if award > 0 else None,
            variance=None,
            max_line_in_period=max_line if max_line > 0 else None,
        )

    # Per-transaction cap
    if restriction.max_expense_per_transaction is not None:
        cap_tx = _money(restriction.max_expense_per_transaction)
        if cap_tx > 0 and max_line > cap_tx:
            return ComplianceResult(
                code=BREACH,
                label=_label(BREACH),
                css=_css(BREACH),
                explanation=f"Largest posted expense line ({max_line}) exceeds max per transaction ({cap_tx}).",
                grant_expense=spend,
                allowed_budget=cap_tx,
                utilization_pct=None,
                variance=max_line - cap_tx,
                max_line_in_period=max_line,
            )
        if cap_tx > 0 and max_line > cap_tx * Decimal("0.9") and max_line <= cap_tx:
            # near per-txn limit
            pass

    # Budget percentage cap of total award
    allowed: Decimal | None = None
    explanation_base = ""
    if restriction.max_budget_percentage is not None and restriction.max_budget_percentage > 0:
        allowed = (award * restriction.max_budget_percentage) / Decimal("100")
        explanation_base = (
            f"Cap {restriction.max_budget_percentage}% of award {award} → allowed {allowed}."
        )
    elif restriction.enforce_budget_validation and restriction.category == DonorRestriction.Category.BUDGET:
        allowed = award
        explanation_base = f"Budget validation: full award {award} used as ceiling."
    elif restriction.restriction_type == DonorRestriction.RestrictionType.BUDGET_CATEGORY_CAP:
        allowed = award
        explanation_base = f"Category cap evaluated against full award {award}."

    if allowed is None or allowed <= 0:
        if award > 0:
            allowed = award
            explanation_base = "No explicit % cap; compared to total award."
        else:
            return ComplianceResult(
                code=NOT_APPLICABLE,
                label=_label(NOT_APPLICABLE),
                css=_css(NOT_APPLICABLE),
                explanation="Award amount is zero; cannot compute utilization.",
                grant_expense=spend,
                allowed_budget=None,
                utilization_pct=None,
                variance=None,
                max_line_in_period=max_line if max_line > 0 else None,
            )

    util = (spend / allowed * Decimal("100")) if allowed > 0 else Decimal("0")
    variance = spend - allowed
    warn_ratio = Decimal("0.9")
    if restriction.compliance_level == DonorRestriction.ComplianceLevel.RECOMMENDED:
        warn_ratio = Decimal("0.95")
    elif restriction.compliance_level == DonorRestriction.ComplianceLevel.INFORMATIONAL:
        warn_ratio = Decimal("0.98")

    code = COMPLIANT
    explanation = f"{explanation_base} Posted expense in period: {spend}; utilization {util:.1f}%."
    if spend > allowed:
        code = BREACH
        explanation = (
            f"{explanation_base} Spend {spend} exceeds allowed {allowed} (over by {variance})."
        )
    elif allowed > 0 and spend > allowed * warn_ratio:
        code = WARNING
        explanation = (
            f"{explanation_base} Spend {spend} is above {warn_ratio * 100:.0f}% of allowed budget ({allowed})."
        )

    return ComplianceResult(
        code=code,
        label=_label(code),
        css=_css(code),
        explanation=explanation,
        grant_expense=spend,
        allowed_budget=allowed,
        utilization_pct=util.quantize(Decimal("0.01")),
        variance=variance.quantize(Decimal("0.01")),
        max_line_in_period=max_line if max_line > 0 else None,
    )
