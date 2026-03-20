from __future__ import annotations

"""
Default data initialization for a freshly migrated tenant database.

All steps are idempotent: safe to run after every deploy or provisioning.

Imports are lazy so management commands work even if an optional app changes.
"""

import logging
from datetime import date

logger = logging.getLogger(__name__)


def _statement_type_for_account_type(account_type: str) -> str:
    from tenant_finance.models import ChartAccount

    if account_type in (ChartAccount.Type.ASSET, ChartAccount.Type.LIABILITY, ChartAccount.Type.EQUITY):
        return ChartAccount.StatementType.BALANCE_SHEET
    if account_type in (ChartAccount.Type.INCOME, ChartAccount.Type.EXPENSE):
        return ChartAccount.StatementType.INCOME_EXPENDITURE
    return ""


def initialize_tenant_defaults(using: str) -> dict[str, bool | str]:
    """
    Run baseline setup on the tenant DB alias.

    Returns a dict of step -> True (did work), False (skipped or already satisfied), or "error".
    """
    results: dict[str, bool | str] = {}

    # --- Finance: currencies + organization singleton ---
    try:
        from tenant_finance.models import OrganizationSettings, ensure_default_currencies

        ensure_default_currencies(using=using)
        results["default_currencies"] = True
        if not OrganizationSettings.objects.using(using).exists():
            OrganizationSettings.objects.using(using).create()
            results["organization_settings"] = True
        else:
            results["organization_settings"] = False
    except Exception as exc:
        logger.exception("tenant_init: finance baseline failed on DB %s", using)
        results["default_currencies"] = "error"
        results["organization_settings"] = "error"
        results["finance_error"] = str(exc)

    # --- Fiscal year: one open calendar year if none exists ---
    try:
        from tenant_finance.models import FiscalYear

        if FiscalYear.objects.using(using).exists():
            results["default_fiscal_year"] = False
        else:
            today = date.today()
            FiscalYear.objects.using(using).create(
                name=f"FY{today.year}",
                start_date=date(today.year, 1, 1),
                end_date=date(today.year, 12, 31),
            )
            results["default_fiscal_year"] = True
    except Exception as exc:
        logger.exception("tenant_init: fiscal year failed on DB %s", using)
        results["default_fiscal_year"] = "error"
        results["fiscal_year_error"] = str(exc)

    # --- Minimal chart-of-accounts scaffold (top-level summary accounts only) ---
    try:
        from tenant_finance.models import ChartAccount

        scaffold = [
            ("1000", "Assets", ChartAccount.Type.ASSET),
            ("2000", "Liabilities", ChartAccount.Type.LIABILITY),
            ("3000", "Equity", ChartAccount.Type.EQUITY),
            ("4000", "Income", ChartAccount.Type.INCOME),
            ("5000", "Expenses", ChartAccount.Type.EXPENSE),
        ]
        created_any = False
        for code, name, acc_type in scaffold:
            st = _statement_type_for_account_type(acc_type)
            _, created = ChartAccount.objects.using(using).get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "type": acc_type,
                    "statement_type": st,
                    "is_active": True,
                },
            )
            created_any = created_any or created
        results["coa_scaffold"] = created_any
    except Exception as exc:
        logger.exception("tenant_init: COA scaffold failed on DB %s", using)
        results["coa_scaffold"] = "error"
        results["coa_error"] = str(exc)

    # --- RBAC templates: optional separate command bootstrap_tenant_rbac ---
    results["rbac_templates"] = False
    results["dashboard_widgets"] = False  # No DashboardWidget model yet; hook for future app

    return results
