"""
Validation rules for Grant funding modality and tranche schedules.

Uses Grant.funding_method (synced from FundingSource payment modality when set) together
with GrantTranche lines for expected receivable schedules, retention splits, and
reimbursement-style tranches.

Used after grant/tranche persistence (multi-db safe).
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError

from tenant_grants.models import Grant, GrantTranche


def _equivalent_percentage(tr: GrantTranche, ceiling: Decimal) -> Decimal:
    if ceiling and ceiling > 0 and tr.amount is not None and tr.amount > 0:
        return ((tr.amount / ceiling) * Decimal("100")).quantize(Decimal("0.0001"))
    if tr.percentage is not None and tr.percentage > 0:
        return tr.percentage
    return Decimal("0")


def tranche_equivalent_percent_sum(tranches: list[GrantTranche], ceiling: Decimal) -> Decimal:
    return sum((_equivalent_percentage(t, ceiling) for t in tranches), Decimal("0"))


def validate_grant_funding_modality(grant: Grant, using: str) -> None:
    """
    Validate funding_method, tranche presence, 100% schedule, and modality-specific rules.

    When Grant.funding_modality (FundingSource) is set, Grant.save() syncs funding_method
    from the catalog modality; retention and reporting flags on the catalog inform controls
    for reimbursement claims and retention balances.
    """
    fm = (grant.funding_method or "").strip()
    valid_fm = {c[0] for c in Grant.FundingMethod.choices}
    if fm and fm not in valid_fm:
        raise ValidationError({"funding_method": "Invalid funding modality."})

    ceiling = grant.grant_ceiling or grant.award_amount or Decimal("0")
    tranches = list(
        GrantTranche.objects.using(using)
        .filter(grant_id=grant.pk)
        .order_by("sort_order", "tranche_no")
    )

    errs: dict[str, list[str]] = {}

    def add(field: str, msg: str) -> None:
        errs.setdefault(field, []).append(msg)

    if grant.status == Grant.Status.ACTIVE and not fm:
        add("funding_method", "Funding modality is required for active grant agreements.")

    if fm in (
        Grant.FundingMethod.ADVANCE_INSTALMENTS,
        Grant.FundingMethod.ADVANCE_WITH_RETENTION,
        Grant.FundingMethod.MIXED,
    ):
        if not tranches:
            add(
                "funding_method",
                "At least one funding tranche is required for this modality.",
            )

    if tranches:
        if ceiling <= 0:
            add("grant_ceiling", "Grant ceiling must be set to validate the tranche schedule.")
        else:
            total_pct = tranche_equivalent_percent_sum(tranches, ceiling)
            if abs(total_pct - Decimal("100")) > Decimal("0.02"):
                add(
                    "__all__",
                    f"Tranche schedule must total 100% of the grant ceiling (currently {total_pct:.4f}%).",
                )

        if fm == Grant.FundingMethod.MIXED:
            for t in tranches:
                if not (t.payment_type or "").strip():
                    add("__all__", "Mixed modality: each tranche must have a payment type.")
                    break
                if not (t.trigger_condition or "").strip():
                    add("__all__", "Mixed modality: each tranche must have a trigger condition.")
                    break

        if fm in (
            Grant.FundingMethod.ADVANCE_INSTALMENTS,
            Grant.FundingMethod.ADVANCE_WITH_RETENTION,
        ):
            for t in tranches:
                if t.payment_type == GrantTranche.PaymentType.ADVANCE and not t.due_date:
                    add(
                        "__all__",
                        "Advance modality: each advance tranche must have a due date.",
                    )
                    break

        if fm == Grant.FundingMethod.ADVANCE_WITH_RETENTION:
            has_adv = any(t.payment_type == GrantTranche.PaymentType.ADVANCE for t in tranches)
            has_ret = any(t.payment_type == GrantTranche.PaymentType.RETENTION for t in tranches)
            if not has_adv or not has_ret:
                add(
                    "funding_method",
                    "Advance with retention: include at least one advance and one retention tranche.",
                )

    if errs:
        raise ValidationError(errs)
