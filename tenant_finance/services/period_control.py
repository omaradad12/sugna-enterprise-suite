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
    if p.status == FiscalPeriod.Status.HARD_CLOSED:
        raise ValueError(
            f"Accounting period is closed (hard closed): {p.name or p.period_name or str(p)}. "
            "Posting is not allowed."
        )
    if p.status == FiscalPeriod.Status.SOFT_CLOSED:
        raise ValueError(
            f"Accounting period is closed (soft closed): {p.name or p.period_name or str(p)}. "
            "Reopen the period before posting."
        )
    if p.status == FiscalPeriod.Status.LOCKED:
        raise ValueError(
            f"Accounting period is locked: {p.name or p.period_name or str(p)}. Posting is not allowed."
        )
    if p.is_closed:
        raise ValueError(
            f"Accounting period is closed: {p.name or p.period_name or str(p)}. Posting is not allowed."
        )
    if p.status != FiscalPeriod.Status.OPEN:
        raise ValueError(
            f"Accounting period is not open (status: {p.get_status_display()}). Posting is not allowed."
        )
    fy = p.fiscal_year
    if fy and (fy.is_closed or fy.status == fy.Status.CLOSED):
        raise ValueError(f"Fiscal year is closed ({fy.name}).")
    return PostingControlResult(
        fiscal_year_id=p.fiscal_year_id,
        accounting_period_id=p.id,
        period_name=p.name or p.period_name or str(p),
    )


def ensure_project_dimension_mapping(*, using: str, project_id: int):
    """
    Ensure a ProjectDimensionMapping row exists for the project (minimal active record).

    Posting requires a mapping when a grant carries a project; new or re-linked projects
    often have none yet. Optional cost center / bank / donor defaults can be filled in
    under Project setup later.
    """
    from tenant_finance.models import ProjectDimensionMapping
    from tenant_grants.models import Project

    proj = Project.objects.using(using).filter(pk=project_id).first()
    if not proj:
        return None
    m, _ = ProjectDimensionMapping.objects.using(using).get_or_create(
        project=proj,
        defaults={"status": ProjectDimensionMapping.Status.ACTIVE},
    )
    return m


def assert_can_post_journal(*, using: str, entry_date: date, grant=None, user=None) -> None:
    """
    Posting control:
    - org accounting period must exist and be open for entry_date
    - if grant/project provided, must be active on entry_date
    """
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
                m = ensure_project_dimension_mapping(using=using, project_id=grant.project_id)
            if not m:
                raise ValueError(
                    "This grant is linked to a project that does not exist, so posting cannot continue."
                )
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

