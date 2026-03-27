"""
Income register: posted receipt vouchers only (read-only list from GL).
"""

from __future__ import annotations

from django.db.models import Q

from tenant_finance.models import JournalEntry


def posted_receipt_voucher_headers(using: str):
    """
    Journal headers for posted receipt vouchers, excluding drafts, reversals, and reversed originals.
    Chronological order: entry_date, id ascending (caller may re-order).
    """
    return (
        JournalEntry.objects.using(using)
        .filter(status=JournalEntry.Status.POSTED)
        .filter(
            Q(source_type=JournalEntry.SourceType.RECEIPT_VOUCHER)
            | Q(journal_type="receipt_voucher")
            | Q(reference__istartswith="RV-"),
        )
        .exclude(Q(source_type=JournalEntry.SourceType.REVERSAL) | Q(journal_type="reversal"))
        .exclude(reference__istartswith="RV-REV-")
        .exclude(reversals__isnull=False)
        .select_related("grant", "grant__donor", "grant__project")
        .distinct()
    )


def infer_receipt_stream_key(je: JournalEntry) -> str:
    """Map journal to register source key (matches ReceiptStream database values)."""
    valid = {c[0] for c in JournalEntry.ReceiptStream.choices}
    rs = (getattr(je, "receipt_stream", None) or "").strip()
    if rs in valid:
        return rs
    if je.grant_id:
        return "grant_funding"
    return "other_income"
