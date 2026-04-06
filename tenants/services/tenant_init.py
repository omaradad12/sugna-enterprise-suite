from __future__ import annotations

"""
Default data initialization for a freshly migrated tenant database.

All steps are idempotent: safe to run after every deploy or provisioning.

Imports are lazy so management commands work even if an optional app changes.

FinancialDimension / FinancialDimensionValue rows are created only on the tenant database using
explicit .using(using) and dimension_id for values — never assign related instances across routers.
"""

import logging
from datetime import date

from django.db import transaction

from tenants.services.provisioning_errors import TenantFinanceInitError

logger = logging.getLogger(__name__)


def _statement_type_for_account_type(account_type: str) -> str:
    from tenant_finance.models import ChartAccount

    if account_type in (ChartAccount.Type.ASSET, ChartAccount.Type.LIABILITY, ChartAccount.Type.EQUITY):
        return ChartAccount.StatementType.BALANCE_SHEET
    if account_type in (ChartAccount.Type.INCOME, ChartAccount.Type.EXPENSE):
        return ChartAccount.StatementType.INCOME_EXPENDITURE
    return ""


def _seed_financial_dimension_defaults(using: str) -> bool:
    """
    Ensure PROG and SECTOR dimensions and baseline values exist (idempotent).
    Uses dimension_id for values to avoid cross-database FK assignment during provisioning.
    """
    from tenant_finance.models import FinancialDimension, FinancialDimensionValue

    created_any = False

    prog_dim, c = FinancialDimension.objects.using(using).get_or_create(
        dimension_code="PROG",
        defaults={
            "dimension_name": "Program",
            "dimension_type": FinancialDimension.DimensionType.PROGRAM,
            "description": "Program dimension for funding/program categories.",
            "status": FinancialDimension.Status.ACTIVE,
        },
    )
    created_any = created_any or c
    prog_defaults = [
        ("PRG-01", "Project grant"),
        ("PRG-02", "Core / institutional"),
        ("PRG-03", "Emergency"),
        ("PRG-04", "Institutional"),
        ("PRG-05", "Other"),
    ]
    pid = prog_dim.pk
    for code, name in prog_defaults:
        _, vc = FinancialDimensionValue.objects.using(using).get_or_create(
            dimension_id=pid,
            code=code,
            defaults={
                "name": name,
                "description": "",
                "status": FinancialDimensionValue.Status.ACTIVE,
            },
        )
        created_any = created_any or vc

    sector_dim, sc = FinancialDimension.objects.using(using).get_or_create(
        dimension_code="SECTOR",
        defaults={
            "dimension_name": "Program sector",
            "dimension_type": FinancialDimension.DimensionType.CLASSIFICATION,
            "description": "Program sector classification values.",
            "status": FinancialDimension.Status.ACTIVE,
        },
    )
    created_any = created_any or sc
    sector_defaults = [
        ("SEC-01", "Health"),
        ("SEC-02", "WASH"),
        ("SEC-03", "Education"),
        ("SEC-04", "Protection"),
        ("SEC-05", "Nutrition"),
        ("SEC-06", "Livelihood"),
        ("SEC-07", "Food Security"),
        ("SEC-08", "Shelter"),
        ("SEC-09", "GBV"),
        ("SEC-10", "Child Protection"),
        ("SEC-11", "Governance"),
        ("SEC-12", "Capacity building"),
        ("SEC-13", "Multi-sector"),
        ("SEC-14", "Other"),
    ]
    sid = sector_dim.pk
    for code, name in sector_defaults:
        _, vc = FinancialDimensionValue.objects.using(using).get_or_create(
            dimension_id=sid,
            code=code,
            defaults={
                "name": name,
                "description": "",
                "status": FinancialDimensionValue.Status.ACTIVE,
            },
        )
        created_any = created_any or vc

    return created_any


def _step(
    step: str,
    using: str,
    fn,
) -> None:
    """Run a provisioning step; raise TenantFinanceInitError with step name on failure."""
    logger.info("tenant_init: step %s database=%s", step, using)
    try:
        fn()
    except TenantFinanceInitError:
        raise
    except Exception as exc:
        logger.exception("tenant_init: step %s failed database=%s", step, using)
        raise TenantFinanceInitError(
            f"Step {step} failed: {exc}",
            model_label=step,
            database=using,
        ) from exc


def initialize_tenant_defaults(using: str) -> dict[str, bool | str]:
    """
    Run baseline setup on the tenant DB alias.

    Runs in a single atomic block on ``using`` so a partial write cannot leave inconsistent setup.

    Returns a dict of step -> True (did work), False (skipped or already satisfied).

    Raises TenantFinanceInitError on failure with model/database context for provisioning logs.
    """
    results: dict[str, bool | str] = {}

    logger.info("tenant_init: starting finance defaults database=%s", using)

    try:
        with transaction.atomic(using=using):

            def step_currencies() -> None:
                from tenant_finance.models import ensure_default_currencies

                ensure_default_currencies(using=using)
                results["default_currencies"] = True

            _step("default_currencies", using, step_currencies)

            def step_org_and_currency_fk() -> None:
                from tenant_finance.models import Currency, OrganizationSettings

                if not OrganizationSettings.objects.using(using).exists():
                    OrganizationSettings.objects.using(using).create()
                    results["organization_settings"] = True
                else:
                    results["organization_settings"] = False
                usd = Currency.objects.using(using).filter(code="USD").first()
                if usd:
                    OrganizationSettings.objects.using(using).filter(default_currency_id__isnull=True).update(
                        default_currency_id=usd.pk
                    )

            _step("organization_settings", using, step_org_and_currency_fk)

            def step_dimensions() -> None:
                results["financial_dimensions"] = _seed_financial_dimension_defaults(using)

            _step("financial_dimensions", using, step_dimensions)

            def step_fiscal_year() -> None:
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

            _step("default_fiscal_year", using, step_fiscal_year)

            def step_coa() -> None:
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

            _step("coa_scaffold", using, step_coa)

            results["rbac_templates"] = False
            results["dashboard_widgets"] = False

    except TenantFinanceInitError:
        raise
    except Exception as exc:
        logger.exception("tenant_init: transaction failed database=%s", using)
        raise TenantFinanceInitError(
            f"Finance defaults transaction failed: {exc}",
            model_label="transaction",
            database=using,
        ) from exc

    logger.info("tenant_init: completed database=%s results=%s", using, results)
    return results
