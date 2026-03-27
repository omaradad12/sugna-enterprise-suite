"""
Outstanding receivables from posted GL lines on receivable accounts.

Uses FIFO application of credits to debits per receivable account so row totals
reconcile with the receivable ledger and GL (sum of outstanding = net DR balance).
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_date

from tenant_finance.models import ChartAccount, JournalEntry, JournalLine
from tenant_finance.receivable_accounts import receivable_accounts_q
from tenant_finance.services.receivables_register import grant_claimable_cap_by_grant_id


def _due_date_for_entry(entry) -> Any:
    return entry.payment_due_date or entry.entry_date


def _debtor_name(entry) -> str:
    if getattr(entry, "donor_id", None) and getattr(entry, "donor", None):
        return entry.donor.name
    grant = getattr(entry, "grant", None)
    if grant and getattr(grant, "donor", None):
        return grant.donor.name
    if entry.memo:
        return entry.memo
    if entry.payee_name:
        return entry.payee_name
    return ""


def _project_label(entry) -> str:
    grant = getattr(entry, "grant", None)
    if not grant:
        return ""
    if grant.project_id and getattr(grant, "project", None):
        return (grant.project.name or "").strip()
    return (grant.project_name or "").strip()


def _grant_code(entry) -> str:
    g = getattr(entry, "grant", None)
    return (g.code or "").strip() if g else ""


def _fund_donor(entry) -> str:
    grant = getattr(entry, "grant", None)
    if grant and getattr(grant, "donor", None):
        return grant.donor.name
    return _debtor_name(entry)


def _fifo_open_chunks(lines: list[JournalLine]) -> list[dict[str, Any]]:
    """Apply credits to debits in chronological order; return open debit chunks."""
    queue: list[dict[str, Any]] = []
    for line in lines:
        d = line.debit or Decimal("0")
        c = line.credit or Decimal("0")
        if d > 0:
            queue.append({"rem": d, "orig": d, "line": line})
        if c > 0:
            rem = c
            while rem > 0 and queue:
                head = queue[0]
                take = min(head["rem"], rem)
                head["rem"] -= take
                rem -= take
                if head["rem"] <= 0:
                    queue.pop(0)
    out: list[dict[str, Any]] = []
    for chunk in queue:
        rem = chunk["rem"]
        if rem > 0:
            orig = chunk["orig"]
            out.append(
                {
                    "orig": orig,
                    "outstanding": rem,
                    "collected": orig - rem,
                    "line": chunk["line"],
                }
            )
    return out


def _apply_grant_claimable_caps(
    raw_chunks: list[dict[str, Any]], tenant_db: str
) -> list[dict[str, Any]]:
    """
    Reduce per-chunk outstanding so total per grant does not exceed remaining claimable
    (eligible receivable minus posted receipts). Entries without a grant are unchanged.
    """
    caps = grant_claimable_cap_by_grant_id(tenant_db)
    remaining: dict[int, Decimal] = {gid: caps.get(gid, Decimal("0")) for gid in caps}

    indexed: list[tuple[tuple, int, dict[str, Any]]] = []
    for i, ch in enumerate(raw_chunks):
        entry = ch["entry"]
        gid = getattr(entry, "grant_id", None)
        if not gid:
            continue
        due = _due_date_for_entry(entry)
        indexed.append(((due, entry.entry_date, entry.id, i), i, ch))

    indexed.sort(key=lambda x: x[0])
    for _k, _i, ch in indexed:
        entry = ch["entry"]
        gid = entry.grant_id
        if not gid:
            continue
        cap_left = remaining.get(gid, Decimal("0"))
        if cap_left <= 0:
            ch["outstanding"] = Decimal("0")
            ch["collected"] = ch.get("orig") or Decimal("0")
            continue
        o = ch["outstanding"] or Decimal("0")
        take = min(o, cap_left)
        ch["outstanding"] = take
        ch["collected"] = (ch.get("orig") or Decimal("0")) - take
        remaining[gid] = cap_left - take

    out: list[dict[str, Any]] = []
    for ch in raw_chunks:
        if (ch.get("outstanding") or Decimal("0")) > 0:
            out.append(ch)
    return out


def _income_by_entry_ids(tenant_db: str, entry_ids: set[int]) -> dict[int, ChartAccount | None]:
    if not entry_ids:
        return {}
    income_by_entry: dict[int, ChartAccount | None] = {}
    income_lines = (
        JournalLine.objects.using(tenant_db)
        .select_related("account")
        .filter(
            entry_id__in=entry_ids,
            entry__status=JournalEntry.Status.POSTED,
            account__type=ChartAccount.Type.INCOME,
            account__is_active=True,
            account__children__isnull=True,
            credit__gt=0,
        )
        .order_by("entry_id", "id")
    )
    for inc in income_lines:
        income_by_entry.setdefault(inc.entry_id, inc.account)
    return income_by_entry


def compute_outstanding_receivable_rows(tenant_db: str, get_params: Any) -> tuple[list[dict[str, Any]], Decimal]:
    """
    Build outstanding receivable rows from posted journal lines (FIFO per account).
    get_params: request.GET-like mapping.
    """
    receivable_ids = list(
        ChartAccount.objects.using(tenant_db).filter(receivable_accounts_q()).values_list("id", flat=True)
    )
    if not receivable_ids:
        return [], Decimal("0")

    qs = (
        JournalLine.objects.using(tenant_db)
        .filter(account_id__in=receivable_ids, entry__status=JournalEntry.Status.POSTED)
        .select_related(
            "entry",
            "entry__grant",
            "entry__grant__donor",
            "entry__grant__project",
            "entry__donor",
            "account",
        )
        .order_by("account_id", "entry__entry_date", "entry__id", "id")
    )
    by_account: dict[int, list[JournalLine]] = defaultdict(list)
    for line in qs:
        by_account[line.account_id].append(line)

    all_entry_ids: set[int] = set()
    raw_chunks: list[dict[str, Any]] = []
    for account_id, acc_lines in by_account.items():
        for ch in _fifo_open_chunks(acc_lines):
            line = ch["line"]
            entry = line.entry
            all_entry_ids.add(entry.id)
            rec_account = line.account
            raw_chunks.append(
                {
                    "orig": ch["orig"],
                    "outstanding": ch["outstanding"],
                    "collected": ch["collected"],
                    "entry": entry,
                    "receivable_account": rec_account,
                }
            )

    raw_chunks = _apply_grant_claimable_caps(raw_chunks, tenant_db)

    income_by_entry = _income_by_entry_ids(tenant_db, all_entry_ids)
    today = timezone.localdate()

    debtor_filter = (get_params.get("debtor") or "").strip()
    project_filter = (get_params.get("project") or "").strip()
    donor_filter = (get_params.get("donor") or "").strip()
    grant_filter = (get_params.get("grant") or "").strip()
    raw_from = (get_params.get("from") or "").strip()
    raw_to = (get_params.get("to") or "").strip()
    from_date = parse_date(raw_from) if raw_from else None
    to_date = parse_date(raw_to) if raw_to else None
    raw_due_from = (get_params.get("due_from") or "").strip()
    raw_due_to = (get_params.get("due_to") or "").strip()
    due_from = parse_date(raw_due_from) if raw_due_from else None
    due_to = parse_date(raw_due_to) if raw_due_to else None
    days_from = get_params.get("days_from")
    days_to = get_params.get("days_to")
    bal_from = get_params.get("balance_from")
    bal_to = get_params.get("balance_to")
    status_filter = (get_params.get("status") or "").strip().lower()

    rows: list[dict[str, Any]] = []
    for ch in raw_chunks:
        entry = ch["entry"]
        balance = ch["outstanding"]
        if balance <= 0:
            continue

        due = _due_date_for_entry(entry)
        recognition_date = entry.entry_date

        if from_date and recognition_date < from_date:
            continue
        if to_date and recognition_date > to_date:
            continue
        if due_from and due < due_from:
            continue
        if due_to and due > due_to:
            continue

        try:
            days_out = (today - due).days
        except Exception:
            days_out = 0

        if days_from is not None and days_from != "":
            try:
                if days_out < int(days_from):
                    continue
            except ValueError:
                pass
        if days_to is not None and days_to != "":
            try:
                if days_out > int(days_to):
                    continue
            except ValueError:
                pass
        if bal_from is not None and bal_from != "":
            try:
                if balance < Decimal(str(bal_from).replace(",", "")):
                    continue
            except Exception:
                pass
        if bal_to is not None and bal_to != "":
            try:
                if balance > Decimal(str(bal_to).replace(",", "")):
                    continue
            except Exception:
                pass

        debtor_name = _debtor_name(entry)
        project_label = _project_label(entry)
        grant_code = _grant_code(entry)
        fund_donor = _fund_donor(entry)

        if debtor_filter and debtor_filter.lower() not in debtor_name.lower():
            continue
        if project_filter and project_filter.lower() not in project_label.lower():
            continue
        if donor_filter and donor_filter.lower() not in fund_donor.lower():
            continue
        if grant_filter and grant_filter.lower() not in grant_code.lower():
            continue

        status_calc = "Open" if due >= today else "Overdue"
        if status_filter and status_filter != status_calc.lower():
            continue

        ref = entry.reference or f"AR-{entry.id:05d}"
        voucher = (entry.source_document_no or entry.reference or ref).strip() or ref
        rows.append(
            {
                "receivable_no": ref,
                "voucher_no": voucher,
                "entry_id": entry.id,
                "debtor_name": debtor_name,
                "project": project_label,
                "grant": grant_code,
                "fund_donor": fund_donor,
                "income_account": income_by_entry.get(entry.id),
                "receivable_account": ch["receivable_account"],
                "original_amount": ch["orig"],
                "amount_collected": ch["collected"],
                "outstanding_balance": balance,
                "due_date": due,
                "status": status_calc,
            }
        )

    rows.sort(key=lambda r: (r["due_date"], r["receivable_no"]))
    total = sum((r.get("outstanding_balance") or Decimal("0")) for r in rows)
    return rows, total
