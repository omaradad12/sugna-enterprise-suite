"""
Grant Financial Reports: budget (grant budget lines), spent (posted GL), remaining.

Budget: sum of BudgetLine.amount per grant (GrantBudgetLine proxy). Not limited by the report period.

Spent: sum of debit amounts on posted journal lines where the account is an expense type,
the effective grant (line.grant or entry.grant) is set, and GL date falls in the selected period.
Includes expenses originating from manual journals, payment vouchers, and other sources that post to JournalLine.

Payment vouchers in this codebase post as JournalEntry + JournalLine (see JournalEntry.source_type).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.models import BigIntegerField, F, Sum
from django.db.models.functions import Coalesce

from tenant_finance.models import ChartAccount, JournalEntry, JournalLine
from tenant_grants.models import BudgetLine, Grant


def grant_budget_totals_by_grant_id(using: str, grant_ids: list[int]) -> dict[int, Decimal]:
    if not grant_ids:
        return {}
    out = {gid: Decimal("0") for gid in grant_ids}
    for row in (
        BudgetLine.objects.using(using)
        .filter(grant_id__in=grant_ids)
        .values("grant_id")
        .annotate(t=Sum("amount"))
    ):
        gid = row["grant_id"]
        out[gid] = row["t"] or Decimal("0")
    return out


def grant_spent_totals_by_grant_id(
    using: str,
    grant_ids: list[int],
    period_start,
    period_end,
) -> dict[int, Decimal]:
    """
    Posted expense debits in [period_start, period_end] on Coalesce(line.grant_id, entry.grant_id).
    """
    if not grant_ids:
        return {}
    base = (
        JournalLine.objects.using(using)
        .filter(
            account__type=ChartAccount.Type.EXPENSE,
            entry__status=JournalEntry.Status.POSTED,
            debit__gt=0,
        )
        .annotate(
            gl_date=Coalesce(F("entry__posting_date"), F("entry__entry_date")),
            eff_grant_id=Coalesce(F("grant_id"), F("entry__grant_id"), output_field=BigIntegerField()),
        )
        .filter(
            eff_grant_id__in=grant_ids,
            gl_date__gte=period_start,
            gl_date__lte=period_end,
        )
    )
    out = {gid: Decimal("0") for gid in grant_ids}
    for row in base.values("eff_grant_id").annotate(total=Sum("debit")):
        gid = row["eff_grant_id"]
        if gid is not None:
            out[gid] = row["total"] or Decimal("0")
    return out


def build_grant_financial_report_rows(
    using: str,
    *,
    period_start,
    period_end,
    donor_id: str | int | None = None,
    grant_id: str | int | None = None,
) -> list[dict[str, Any]]:
    grants_qs = Grant.objects.using(using).select_related("donor").order_by("code")
    if donor_id not in (None, ""):
        grants_qs = grants_qs.filter(donor_id=donor_id)
    if grant_id not in (None, ""):
        grants_qs = grants_qs.filter(pk=grant_id)

    grants_list = list(grants_qs)
    gids = [g.pk for g in grants_list]
    budget_map = grant_budget_totals_by_grant_id(using, gids)
    spent_map = grant_spent_totals_by_grant_id(using, gids, period_start, period_end)

    rows: list[dict[str, Any]] = []
    for g in grants_list:
        budget = budget_map.get(g.pk, Decimal("0"))
        spent = spent_map.get(g.pk, Decimal("0"))
        rows.append(
            {
                "grant": g,
                "budget": budget,
                "spent": spent,
                "remaining": budget - spent,
            }
        )
    return rows
