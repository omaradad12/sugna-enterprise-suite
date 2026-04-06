"""
Detect duplicate finance transactions for the same business event.

Duplicate = same transaction type (source_type + journal_type + receipt_stream), entry date,
total debit amount, payee, normalized reference, and project.

Posted duplicates are blocked on post. Excel import rejects within-file duplicates and rows
matching an already-posted duplicate.
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

_AUTO_DOC_REF_RE = re.compile(r"^(pv|rv|je|gj|adj|ift|rev)-\d+$", re.IGNORECASE)


def normalize_payee(name: str) -> str:
    return " ".join((name or "").strip().casefold().split())


def normalize_reference_for_duplicate(source_document_no: str, reference: str) -> str:
    ref = ((source_document_no or "").strip() or (reference or "").strip())
    if _AUTO_DOC_REF_RE.match(ref):
        return ""
    return ref.casefold()


def transaction_type_key(entry: Any) -> str:
    st = (getattr(entry, "source_type", None) or getattr(entry, "source", None) or "").strip().lower()
    jt = (getattr(entry, "journal_type", None) or "").strip().lower()
    rs = (getattr(entry, "receipt_stream", None) or "").strip().lower()
    return f"{st}|{jt}|{rs}"


def effective_project_id(*, entry: Any, using: str) -> int | None:
    if getattr(entry, "project_id", None):
        return int(entry.project_id)
    if entry.grant_id:
        g = getattr(entry, "grant", None)
        if g is not None and getattr(g, "project_id", None):
            return int(g.project_id)
        from tenant_grants.models import Grant

        pid = (
            Grant.objects.using(using)
            .filter(pk=entry.grant_id)
            .values_list("project_id", flat=True)
            .first()
        )
        return int(pid) if pid else None
    return None


def line_debit_total(*, using: str, entry_id: int) -> Decimal:
    from django.db.models import Sum

    from tenant_finance.models import JournalLine

    s = (
        JournalLine.objects.using(using)
        .filter(entry_id=entry_id)
        .aggregate(total=Sum("debit"))
        .get("total")
    )
    return (s or Decimal("0")).quantize(Decimal("0.01"))


def fingerprint_tuple_for_entry(*, entry: Any, using: str, debit_total: Decimal | None = None) -> tuple:
    if debit_total is None and entry.pk:
        debit_total = line_debit_total(using=using, entry_id=entry.pk)
    elif debit_total is None:
        debit_total = Decimal("0").quantize(Decimal("0.01"))
    else:
        debit_total = Decimal(debit_total).quantize(Decimal("0.01"))
    pid = effective_project_id(entry=entry, using=using)
    return (
        transaction_type_key(entry),
        entry.entry_date,
        debit_total,
        normalize_payee(getattr(entry, "payee_name", "") or ""),
        normalize_reference_for_duplicate(
            getattr(entry, "source_document_no", "") or "",
            getattr(entry, "reference", "") or "",
        ),
        pid,
    )


def fingerprint_from_import_row(
    *,
    source_type: str,
    journal_type: str,
    receipt_stream: str,
    entry_date,
    amount: Decimal,
    payee_name: str,
    source_document_no: str,
    reference: str,
    project_id: int | None,
) -> tuple:
    amt = Decimal(amount or 0).quantize(Decimal("0.01"))
    st = (source_type or "").strip().lower()
    jt = (journal_type or "").strip().lower()
    rs = (receipt_stream or "").strip().lower()
    txn_key = f"{st}|{jt}|{rs}"
    return (
        txn_key,
        entry_date,
        amt,
        normalize_payee(payee_name),
        normalize_reference_for_duplicate(source_document_no, reference),
        project_id,
    )


def find_posted_duplicate(
    *,
    using: str,
    fingerprint: tuple,
    exclude_entry_id: int | None = None,
) -> Any | None:
    from django.db.models import Prefetch

    from tenant_finance.models import JournalEntry, JournalLine

    _txn_key, ed, _amt, _payee, _ref, _proj_id = fingerprint
    qs = (
        JournalEntry.objects.using(using)
        .filter(status=JournalEntry.Status.POSTED, entry_date=ed)
        .select_related("grant")
        .prefetch_related(Prefetch("lines", queryset=JournalLine.objects.only("debit", "credit")))
    )
    if exclude_entry_id:
        qs = qs.exclude(pk=exclude_entry_id)
    for cand in qs.order_by("-pk")[:500]:
        tot = sum((ln.debit or Decimal("0")) for ln in cand.lines.all()).quantize(Decimal("0.01"))
        fp2 = fingerprint_tuple_for_entry(entry=cand, using=using, debit_total=tot)
        if fp2 == fingerprint:
            return cand
    return None


def assert_no_posted_duplicate(*, using: str, entry: Any, exclude_entry_id: int | None = None) -> None:
    from django.utils.translation import gettext as _

    from tenant_finance.models import JournalEntry

    if (getattr(entry, "status", None) or "") != JournalEntry.Status.POSTED:
        return
    eid = exclude_entry_id if exclude_entry_id is not None else getattr(entry, "pk", None)
    if not eid:
        return
    fp = fingerprint_tuple_for_entry(entry=entry, using=using)
    other = find_posted_duplicate(using=using, fingerprint=fp, exclude_entry_id=eid)
    if other:
        ref = (getattr(other, "reference", None) or getattr(other, "source_document_no", None) or "").strip()
        raise ValueError(
            _("Duplicate transaction: matches already posted entry %(ref)s (same type, date, amount, payee, reference, and project).")
            % {"ref": ref or f"#{other.pk}"}
        )
