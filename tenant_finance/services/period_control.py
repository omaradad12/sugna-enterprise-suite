from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class PostingControlResult:
    fiscal_year_id: int
    accounting_period_id: int
    period_name: str


def get_open_period_for_date(*, using: str, dt: date) -> PostingControlResult:
    from tenant_finance.models import FiscalPeriod

    p = (
        FiscalPeriod.objects.using(using)
        .select_related("fiscal_year")
        .filter(start_date__lte=dt, end_date__gte=dt)
        .order_by("start_date")
        .first()
    )
    if not p:
        raise ValueError("No accounting period exists for this transaction date.")
    # Hard close blocks posting at engine level; soft close handled with role exceptions via assert_can_post_journal.
    if p.status == FiscalPeriod.Status.HARD_CLOSED or (p.is_closed and p.status != FiscalPeriod.Status.SOFT_CLOSED):
        raise ValueError(f"Accounting period is hard closed ({p.name or p.period_name or str(p)}).")
    fy = p.fiscal_year
    if fy and (fy.is_closed or fy.status == fy.Status.CLOSED):
        raise ValueError(f"Fiscal year is closed ({fy.name}).")
    return PostingControlResult(
        fiscal_year_id=p.fiscal_year_id,
        accounting_period_id=p.id,
        period_name=p.name or p.period_name or str(p),
    )


def assert_can_post_journal(*, using: str, entry_date: date, grant=None, user=None) -> None:
    """
    Posting control:
    - org accounting period must exist and be open for entry_date
    - if grant/project provided, must be active on entry_date
    """
    # Enforce open/soft/hard close semantics (soft close may allow limited posting)
    from tenant_finance.services.accounting_periods import assert_can_post

    assert_can_post(using=using, dt=entry_date, user=user)

    if grant is None:
        return

    # Uses new helper methods if present, otherwise falls back to legacy fields.
    if hasattr(grant, "is_active_on"):
        if not grant.is_active_on(entry_date):
            raise ValueError("Grant (and its project) must be active for the transaction date.")
        # Require an active project mapping when a project is linked (enterprise posting control)
        if getattr(grant, "project_id", None):
            from tenant_finance.models import ProjectDimensionMapping

            m = (
                ProjectDimensionMapping.objects.using(using)
                .select_related("project")
                .filter(project_id=grant.project_id)
                .first()
            )
            if not m:
                raise ValueError("No project mapping is configured for this project. Configure Default Mapping first.")
            if hasattr(m, "is_active_on") and not m.is_active_on(entry_date):
                raise ValueError("Project mapping is inactive or outside its active period for this transaction date.")
        return

    # Legacy fallback (should be rare once migrations applied)
    if getattr(grant, "status", "") != "active":
        raise ValueError("Only active grants can be used in transactions.")
    if getattr(grant, "start_date", None) and entry_date < grant.start_date:
        raise ValueError("Transaction date must be on or after grant start date.")
    if getattr(grant, "end_date", None) and entry_date > grant.end_date:
        raise ValueError("Transaction date must be on or before grant end date.")
    if getattr(grant, "project_id", None) and hasattr(grant.project, "is_active_on"):
        if not grant.project.is_active_on(entry_date):
            raise ValueError("Project must be active for the transaction date.")

