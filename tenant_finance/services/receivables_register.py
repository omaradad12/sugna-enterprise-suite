"""
Receivables register: derive totals and receipt dates from posted receipt vouchers only.

Draft receipts are excluded. Reversed originals (linked reversal journal) are excluded.
Reversal journals are never counted as receipts. Values are recomputed on each read
(post, edit, reverse all reflected on next load).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.models import Q, Sum


def grant_receipt_totals_by_grant_id(using: str) -> dict[int, dict[str, Any]]:
    """
    Per grant:
    - total_received: sum of income credits (leaf income accounts) on posted receipt vouchers.
    - first_receipt_date / latest_receipt_date: min/max entry_date on those vouchers (receipt date).

    Excludes draft/pending/approved (non-posted), reversal journals, and originals that have
    been reversed (see JournalEntry.reversed_by / reversals).
    """
    from tenant_finance.models import ChartAccount, JournalEntry, JournalLine

    posted_receipts = (
        JournalEntry.objects.using(using)
        .filter(
            grant__isnull=False,
            status=JournalEntry.Status.POSTED,
        )
        .filter(
            Q(source_type=JournalEntry.SourceType.RECEIPT_VOUCHER)
            | Q(journal_type="receipt_voucher")
            | Q(reference__istartswith="RV-"),
        )
        .exclude(Q(source_type=JournalEntry.SourceType.REVERSAL) | Q(journal_type="reversal"))
        .exclude(reference__istartswith="RV-REV-")
        .exclude(reversals__isnull=False)
        .distinct()
    )

    stats: dict[int, dict[str, Any]] = {}
    for je in posted_receipts.select_related("grant"):
        gid = je.grant_id
        if not gid:
            continue

        amount = (
            JournalLine.objects.using(using)
            .filter(
                entry=je,
                account__type=ChartAccount.Type.INCOME,
                account__is_active=True,
                account__children__isnull=True,
                credit__gt=0,
            )
            .aggregate(t=Sum("credit"))
            .get("t")
            or Decimal("0")
        )
        if amount <= 0:
            continue

        rec = stats.setdefault(
            gid,
            {
                "total_received": Decimal("0"),
                "first_receipt_date": None,
                "latest_receipt_date": None,
            },
        )
        rec["total_received"] += amount
        d = je.entry_date
        if rec["first_receipt_date"] is None or d < rec["first_receipt_date"]:
            rec["first_receipt_date"] = d
        if rec["latest_receipt_date"] is None or d > rec["latest_receipt_date"]:
            rec["latest_receipt_date"] = d

    return stats


def remaining_claimable_receivable(eligible: Decimal, total_received: Decimal) -> Decimal:
    """Cash still claimable from donor: eligible receivable cap minus posted receipts (not below zero)."""
    return max(eligible - total_received, Decimal("0"))


def grant_claimable_cap_by_grant_id(using: str) -> dict[int, Decimal]:
    """
    Per grant: max amount still claimable (effective eligible minus posted receipt income), floored at zero.
    Effective eligible applies funding modality and tranche unlock rules (see receivable_modality).
    """
    from tenant_grants.models import Grant
    from tenant_grants.services.receivable_modality import effective_eligible_for_claimable

    stats = grant_receipt_totals_by_grant_id(using)
    out: dict[int, Decimal] = {}
    qs = (
        Grant.objects.using(using)
        .prefetch_related("tranches")
        .only(
            "id",
            "eligible_receivable_amount",
            "grant_ceiling",
            "award_amount",
            "funding_method",
            "signed_date",
            "expense_report_approved",
            "audit_approved",
            "final_report_approved",
        )
    )
    for g in qs:
        eligible = effective_eligible_for_claimable(g)
        rec = stats.get(g.id)
        received = rec["total_received"] if rec else Decimal("0")
        out[g.id] = remaining_claimable_receivable(eligible, received)
    return out
