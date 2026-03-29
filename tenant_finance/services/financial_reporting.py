"""
Shared rules for financial statements: posted-only activity, grant scope, cash scope, validation helpers.
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import DateField, Q, QuerySet, Sum
from django.db.models.functions import Coalesce

_REPORT_EPS = Decimal("0.02")


def journal_line_gl_date_annotation():
    """Effective GL date: posting date when posted, else entry date."""
    from tenant_finance.models import JournalEntry, JournalLine

    return Coalesce(
        "entry__posting_date",
        "entry__entry_date",
        output_field=DateField(),
    )


def posted_journal_lines(using: str) -> QuerySet:
    from tenant_finance.models import JournalEntry, JournalLine

    return (
        JournalLine.objects.using(using)
        .select_related("entry", "account")
        .annotate(gl_date=journal_line_gl_date_annotation())
        .filter(entry__status=JournalEntry.Status.POSTED)
    )


def user_sees_all_grants(user, tenant_db: str) -> bool:
    from rbac.models import user_has_permission

    return user_has_permission(user, "finance:scope.all_grants", using=tenant_db)


def assigned_grant_ids(user, tenant_db: str) -> list[int]:
    try:
        return list(user.assigned_grants.using(tenant_db).values_list("id", flat=True))
    except Exception:
        return []


def restrict_journal_lines_by_grant_scope(qs: QuerySet, user, tenant_db: str) -> QuerySet:
    """
    Users without finance:scope.all_grants only see lines tied to their assigned grants
    (header grant or line grant).
    """
    if user_sees_all_grants(user, tenant_db):
        return qs
    allowed = assigned_grant_ids(user, tenant_db)
    if not allowed:
        # No grant assignments: still show organizational lines (no grant on entry or line).
        return qs.filter(Q(entry__grant_id__isnull=True) & Q(grant_id__isnull=True))
    return qs.filter(Q(entry__grant_id__in=allowed) | Q(grant_id__in=allowed))


def assert_grant_filter_allowed(user, tenant_db: str, grant_id: int | None) -> bool:
    if not grant_id:
        return True
    if user_sees_all_grants(user, tenant_db):
        return True
    return grant_id in assigned_grant_ids(user, tenant_db)


def cash_and_bank_chart_account_ids(using: str) -> list[int]:
    """Chart accounts for CFS: active bank books plus asset accounts in CASH/BANK categories."""
    from tenant_finance.services.cash_flow_statement import cash_and_bank_chart_account_ids_extended

    return cash_and_bank_chart_account_ids_extended(using)


def filter_grants_for_report_dropdown(qs, user, tenant_db: str):
    if user_sees_all_grants(user, tenant_db):
        return qs
    ids = assigned_grant_ids(user, tenant_db)
    if not ids:
        return qs.none()
    return qs.filter(pk__in=ids)


def is_balanced_debit_credit(total_debit: Decimal, total_credit: Decimal) -> bool:
    return abs((total_debit or Decimal("0")) - (total_credit or Decimal("0"))) <= _REPORT_EPS


def statement_equation_delta(assets: Decimal, liabilities_plus_equity: Decimal) -> Decimal:
    return (assets or Decimal("0")) - (liabilities_plus_equity or Decimal("0"))


def opening_balances_totals(using: str) -> tuple[Decimal, Decimal]:
    from tenant_finance.models import OpeningBalance

    agg = OpeningBalance.objects.using(using).aggregate(
        td=Sum("debit"),
        tc=Sum("credit"),
    )
    return (agg.get("td") or Decimal("0"), agg.get("tc") or Decimal("0"))


def fiscal_year_containing(using: str, d):
    from tenant_finance.models import FiscalYear

    return (
        FiscalYear.objects.using(using)
        .filter(start_date__lte=d, end_date__gte=d)
        .order_by("-start_date")
        .first()
    )
