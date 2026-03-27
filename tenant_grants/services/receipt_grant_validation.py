"""Enforce grant ceiling and eligible (modality) limits when posting receipt vouchers."""

from __future__ import annotations

from decimal import Decimal

from tenant_finance.services.receivables_register import grant_receipt_totals_by_grant_id
from tenant_grants.models import Grant
from tenant_grants.services.receivable_modality import effective_eligible_for_claimable


def get_receipt_voucher_credit_amount(entry) -> Decimal:
    """Total credit amount on the journal (receipt voucher is balanced one Dr / one Cr)."""
    from django.db.models import Sum

    from tenant_finance.models import JournalLine

    t = (
        JournalLine.objects.using(entry._state.db or "default")
        .filter(entry_id=entry.pk)
        .aggregate(s=Sum("credit"))
        .get("s")
    )
    return t or Decimal("0")


def assert_grant_receipt_posting_allowed(
    *,
    using: str,
    grant: Grant,
    receipt_amount: Decimal,
) -> None:
    """
    Block posting when cumulative posted receipts would exceed grant ceiling or effective eligible.
    """
    if receipt_amount <= 0:
        return

    g = Grant.objects.using(using).prefetch_related("tranches").get(pk=grant.pk)
    stats = grant_receipt_totals_by_grant_id(using)
    received = stats.get(g.id, {}).get("total_received") or Decimal("0")
    new_total = received + receipt_amount

    ceiling = g.grant_ceiling or g.award_amount or Decimal("0")
    if ceiling > 0 and new_total > ceiling:
        raise ValueError(
            f"Posted receipts for this grant would exceed the grant ceiling ({ceiling:,.2f}). "
            f"Already received: {received:,.2f}; this receipt: {receipt_amount:,.2f}."
        )

    eff = effective_eligible_for_claimable(g)
    if new_total > eff:
        raise ValueError(
            f"Posted receipts would exceed the eligible amount for this funding modality ({eff:,.2f}). "
            f"Already received: {received:,.2f}; this receipt: {receipt_amount:,.2f}. "
            "Adjust eligible receivable, tranche schedule, or approvals."
        )
