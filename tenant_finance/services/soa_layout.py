"""
Statement of Activities: income by category; expenditure by NGO bucket (program / admin / support).
Uses account category codes from seeded NGO chart (extend mappings as tenants add categories).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

# Expense category codes → reporting bucket
PROGRAM_EXPENSE_CODES: frozenset[str] = frozenset({"PROGRAM_EXP"})
ADMINISTRATIVE_EXPENSE_CODES: frozenset[str] = frozenset({"STAFF_COSTS", "OPER_EXP"})
SUPPORT_COST_EXPENSE_CODES: frozenset[str] = frozenset({"FINANCE_COSTS"})


def income_display_amount(bal: Any) -> Any:
    """Journal lines use debit−credit; income is credit-normal → show as positive revenue."""
    return -bal if bal is not None else bal


def expense_bucket_for_category(cat_code: str | None) -> str:
    c = (cat_code or "").strip().upper()
    if c in PROGRAM_EXPENSE_CODES:
        return "program"
    if c in SUPPORT_COST_EXPENSE_CODES:
        return "support"
    if c in ADMINISTRATIVE_EXPENSE_CODES:
        return "administrative"
    # Custom / legacy codes: default to administrative so nothing is dropped
    return "administrative"


def group_income_by_category(income_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ordered sections: each {category_label, lines: [(code, name, amt)], subtotal}."""
    buckets: dict[str, list[tuple]] = defaultdict(list)
    meta: dict[str, tuple[int, str]] = {}

    for r in income_rows:
        cat_code = (r.get("account__category__code") or "").strip()
        label = (r.get("account__category__name") or "").strip() or "Uncategorized"
        disp = r.get("account__category__display_order")
        try:
            disp_i = int(disp) if disp is not None else 999
        except (TypeError, ValueError):
            disp_i = 999
        key = cat_code or "__uncat__"
        if key not in meta:
            meta[key] = (disp_i, label)
        amt = income_display_amount(r["bal"])
        buckets[key].append((r["account__code"], r["account__name"], amt))

    out: list[dict[str, Any]] = []
    for key in sorted(buckets.keys(), key=lambda k: (meta[k][0], meta[k][1].lower())):
        lines = sorted(buckets[key], key=lambda x: (x[0] or ""))
        subtotal = sum(x[2] for x in lines)
        out.append(
            {
                "category_label": meta[key][1],
                "lines": lines,
                "subtotal": subtotal,
            }
        )
    return out


def partition_expenses_by_bucket(expense_rows: list[dict[str, Any]]) -> tuple[list[tuple], list[tuple], list[tuple]]:
    program: list[tuple] = []
    administrative: list[tuple] = []
    support: list[tuple] = []

    for r in expense_rows:
        cat = r.get("account__category__code")
        bucket = expense_bucket_for_category(cat)
        amt = r["bal"]
        t = (r["account__code"], r["account__name"], amt)
        if bucket == "program":
            program.append(t)
        elif bucket == "support":
            support.append(t)
        else:
            administrative.append(t)

    program.sort(key=lambda x: x[0] or "")
    administrative.sort(key=lambda x: x[0] or "")
    support.sort(key=lambda x: x[0] or "")
    return program, administrative, support
