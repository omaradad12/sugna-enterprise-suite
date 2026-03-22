"""
Statement of Financial Position: map chart accounts into current / non-current sections
using account category codes (seeded NGO defaults + common extensions).
"""

from __future__ import annotations

from typing import Any

# Seeded category FIXED_ASSETS → non-current; other asset categories default to current.
NON_CURRENT_ASSET_CATEGORY_CODES: frozenset[str] = frozenset({"FIXED_ASSETS"})

# Extend when tenants add long-term liability categories (standard NGO / IPSAS-style).
NON_CURRENT_LIABILITY_CATEGORY_CODES: frozenset[str] = frozenset(
    {
        "LONG_TERM_DEBT",
        "NOTES_PAYABLE_LONG",
        "BONDS_PAYABLE",
        "LEASE_LIABILITY_NONCURRENT",
        "DEFERRED_REVENUE_NONCURRENT",
    }
)


def account_row_tuple(r: dict[str, Any]) -> tuple[str, str, Any]:
    return (r["account__code"], r["account__name"], r["bal"])


def partition_assets(rows: list[dict[str, Any]]) -> tuple[list[tuple], list[tuple]]:
    current: list[tuple] = []
    non_current: list[tuple] = []
    for r in rows:
        t = account_row_tuple(r)
        code = (r.get("account__category__code") or "").strip().upper()
        if code in NON_CURRENT_ASSET_CATEGORY_CODES:
            non_current.append(t)
        else:
            current.append(t)
    return current, non_current


def partition_liabilities(rows: list[dict[str, Any]]) -> tuple[list[tuple], list[tuple]]:
    current: list[tuple] = []
    non_current: list[tuple] = []
    for r in rows:
        t = account_row_tuple(r)
        code = (r.get("account__category__code") or "").strip().upper()
        if code in NON_CURRENT_LIABILITY_CATEGORY_CODES:
            non_current.append(t)
        else:
            current.append(t)
    return current, non_current


def sum_amounts(lines: list[tuple]) -> Any:
    return sum(x[2] for x in lines)
