"""
Cash flow statement (IFRS-style): cash and bank only, posted journals, activity classification.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Literal

from django.db.models import Q, QuerySet, Sum

Bucket = Literal["operating", "investing", "financing"]


def cash_and_bank_chart_account_ids_extended(using: str) -> list[int]:
    """
    Chart accounts that represent cash and bank balances:
    - Linked to a BankAccount master row (active or inactive; historical activity remains in scope), and/or
    - Asset accounts whose category code is CASH or BANK (case-insensitive).
    """
    from tenant_finance.models import BankAccount, ChartAccount

    ids: set[int] = set(
        BankAccount.objects.using(using)
        .values_list("account_id", flat=True)
        .distinct()
    )
    cat_q = Q(category__code__iexact="CASH") | Q(category__code__iexact="BANK")
    ids.update(
        ChartAccount.objects.using(using)
        .filter(is_active=True, type=ChartAccount.Type.ASSET)
        .filter(cat_q)
        .values_list("id", flat=True)
    )
    return sorted(ids)


def _norm(s: str | None) -> str:
    return (s or "").strip().upper()


def classify_journal_entry_cash_bucket(
    non_cash_lines: list,
) -> Bucket:
    """
    Classify cash effect of a journal from its non-cash lines (IFRS-style heuristic).
    Priority: financing (equity / borrowings) > investing (long-term assets) > operating.
    """
    from tenant_finance.models import ChartAccount

    if not non_cash_lines:
        return "operating"

    def line_info(ln):
        acc = ln.account
        cat = getattr(acc, "category", None)
        code = _norm(getattr(cat, "code", None))
        name = (getattr(acc, "name", None) or "").lower()
        typ = getattr(acc, "type", None)
        return typ, code, name

    financing_hits = 0
    investing_hits = 0
    for typ, code, name in (line_info(ln) for ln in non_cash_lines):
        if typ == ChartAccount.Type.EQUITY:
            financing_hits += 1
        if typ == ChartAccount.Type.LIABILITY:
            if code in ("LOAN", "BORROWING", "DEBT", "FINANCING") or any(
                k in name for k in ("loan", "borrowing", "debt", "note payable", "lease liability")
            ):
                financing_hits += 1
        if typ == ChartAccount.Type.ASSET:
            if code in ("FIXED_ASSETS", "FIXED_ASSET", "PPE", "INVESTMENT", "LONG_TERM_INVESTMENT"):
                investing_hits += 1
            elif any(
                k in name
                for k in (
                    "property",
                    "plant",
                    "equipment",
                    "fixed asset",
                    "investment property",
                    "long-term investment",
                )
            ):
                investing_hits += 1

    if financing_hits:
        return "financing"
    if investing_hits:
        return "investing"
    return "operating"


def compute_cash_flow_buckets(
    *,
    tenant_db: str,
    period_start,
    period_end,
    cash_account_ids: list[int],
    base_journal_lines: QuerySet,
) -> tuple[
    dict[Bucket, Decimal],
    dict[Bucket, list[dict]],
    Decimal,
]:
    """
    Returns:
      - bucket_totals: operating / investing / financing sums (cash leg: debit - credit on cash accounts)
      - bucket_details: list of entry summaries per bucket for drill-down
      - net_change: sum of the three buckets (excludes pure intra-cash transfers where net is 0)
    """
    from tenant_finance.models import JournalLine

    if not cash_account_ids:
        return (
            {"operating": Decimal("0"), "investing": Decimal("0"), "financing": Decimal("0")},
            {"operating": [], "investing": [], "financing": []},
            Decimal("0"),
        )

    cash_set = frozenset(cash_account_ids)
    period_cash = base_journal_lines.filter(
        gl_date__gte=period_start,
        gl_date__lte=period_end,
        account_id__in=cash_account_ids,
    )
    entry_ids = list(period_cash.values_list("entry_id", flat=True).distinct())
    if not entry_ids:
        return (
            {"operating": Decimal("0"), "investing": Decimal("0"), "financing": Decimal("0")},
            {"operating": [], "investing": [], "financing": []},
            Decimal("0"),
        )

    all_lines = (
        JournalLine.objects.using(tenant_db)
        .filter(entry_id__in=entry_ids)
        .select_related("entry", "account", "account__category")
    )

    by_entry: dict[int, list] = defaultdict(list)
    for ln in all_lines:
        by_entry[ln.entry_id].append(ln)

    bucket_totals: dict[Bucket, Decimal] = {
        "operating": Decimal("0"),
        "investing": Decimal("0"),
        "financing": Decimal("0"),
    }
    bucket_details: dict[Bucket, list[dict]] = {"operating": [], "investing": [], "financing": []}

    for eid, elines in by_entry.items():
        cash_net = sum(
            (ln.debit or Decimal("0")) - (ln.credit or Decimal("0"))
            for ln in elines
            if ln.account_id in cash_set
        )
        if cash_net == 0:
            continue
        non_cash = [ln for ln in elines if ln.account_id not in cash_set]
        bucket = classify_journal_entry_cash_bucket(non_cash)
        bucket_totals[bucket] += cash_net
        entry = elines[0].entry
        ref = (getattr(entry, "source_document_no", None) or "").strip() or (
            getattr(entry, "reference", None) or ""
        ).strip()
        label = ref or f"JE-{eid}"
        memo = (getattr(entry, "memo", None) or "").strip()
        gl_date = getattr(entry, "posting_date", None) or getattr(entry, "entry_date", None)
        bucket_details[bucket].append(
            {
                "entry_id": eid,
                "label": label,
                "memo": memo,
                "amount": cash_net,
                "gl_date": gl_date,
            }
        )

    for b in bucket_details:
        bucket_details[b].sort(key=lambda r: (r.get("gl_date") or period_start, r["entry_id"]))

    net_change = bucket_totals["operating"] + bucket_totals["investing"] + bucket_totals["financing"]
    return bucket_totals, bucket_details, net_change


def cash_roll_forward(
    *,
    base_journal_lines: QuerySet,
    cash_account_ids: list[int],
    period_start,
    period_end,
) -> tuple[Decimal, Decimal, Decimal]:
    """Opening (before period_start), closing (<= period_end), net period movement on cash accounts."""

    def _cash_net(q):
        if not cash_account_ids:
            return Decimal("0")
        agg = q.filter(account_id__in=cash_account_ids).aggregate(
            sde=Sum("debit"), scr=Sum("credit")
        )
        return (agg.get("sde") or Decimal("0")) - (agg.get("scr") or Decimal("0"))

    opening = _cash_net(base_journal_lines.filter(gl_date__lt=period_start))
    closing = _cash_net(base_journal_lines.filter(gl_date__lte=period_end))
    period_movement = _cash_net(
        base_journal_lines.filter(gl_date__gte=period_start, gl_date__lte=period_end)
    )
    return opening, closing, period_movement
