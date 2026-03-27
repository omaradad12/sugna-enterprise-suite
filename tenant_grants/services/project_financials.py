"""
Aggregated budget, spend, and remaining balances per Project (from linked Grants and GL).
Single source of truth: BudgetLine sums and posted JournalLine expense per grant.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tenant_grants.models import Project

from django.db.models import Sum


def _grant_budget_total(using: str, grant) -> Decimal:
    """Prefer sum of approved budget lines; fallback to grant award amount."""
    from tenant_grants.models import BudgetLine

    bl = (
        BudgetLine.objects.using(using)
        .filter(grant_id=grant.pk)
        .aggregate(t=Sum("amount"))
        .get("t")
    )
    if bl is not None and bl > 0:
        return bl
    return grant.award_amount or Decimal("0")


def project_financial_rollups(using: str, project_ids: list[int]) -> dict[int, dict]:
    """
    Per project_id:
      grant_count, total_budget, total_spent, remaining,
      primary_currency (code or None) from first grant with currency.
    """
    from tenant_finance.models import get_grant_posted_expense_total
    from tenant_grants.models import Grant

    if not project_ids:
        return {}

    grants = (
        Grant.objects.using(using)
        .filter(project_id__in=project_ids)
        .select_related("currency")
    )
    by_project: dict[int, list] = defaultdict(list)
    for g in grants:
        by_project[g.project_id].append(g)

    out: dict[int, dict] = {}
    for pid in project_ids:
        glist = by_project.get(pid) or []
        total_budget = Decimal("0")
        total_spent = Decimal("0")
        primary_currency = None
        for g in glist:
            total_budget += _grant_budget_total(using, g)
            total_spent += get_grant_posted_expense_total(g.pk, using) or Decimal("0")
            if primary_currency is None and g.currency_id:
                primary_currency = g.currency
        remaining = total_budget - total_spent
        util_pct: Decimal | None
        if total_budget > 0:
            util_pct = (total_spent / total_budget) * Decimal("100")
        else:
            util_pct = None
        out[pid] = {
            "grant_count": len(glist),
            "total_budget": total_budget,
            "total_spent": total_spent,
            "remaining": remaining,
            "primary_currency": primary_currency,
            "utilization_pct": util_pct,
        }
    return out


def aggregate_project_financial_rollups(roll: dict[int, dict]) -> dict:
    """Sum budget, spent, remaining, grant links across projects; overall utilization %."""
    tb = ts = tr = Decimal("0")
    gc = 0
    for v in roll.values():
        tb += v.get("total_budget") or Decimal("0")
        ts += v.get("total_spent") or Decimal("0")
        tr += v.get("remaining") or Decimal("0")
        gc += int(v.get("grant_count") or 0)
    up = (ts / tb * Decimal("100")) if tb > 0 else None
    return {
        "total_budget": tb,
        "total_spent": ts,
        "remaining": tr,
        "grant_count": gc,
        "utilization_pct": up,
    }


def attach_project_financials(projects: list, using: str) -> None:
    """Mutate each Project in list with .fin rollup dict (template-safe; no leading underscore)."""
    ids = [p.pk for p in projects if getattr(p, "pk", None)]
    roll = project_financial_rollups(using, ids)
    for p in projects:
        p.fin = roll.get(
            p.pk,
            {
                "grant_count": 0,
                "total_budget": Decimal("0"),
                "total_spent": Decimal("0"),
                "remaining": Decimal("0"),
                "primary_currency": None,
                "utilization_pct": None,
            },
        )
