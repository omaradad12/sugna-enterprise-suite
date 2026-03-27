"""
Project operational end dates: alert states, closure guards, and permission helpers.

Aligns with grant compliance: receivable balances, unposted journals, and budget lines
before closure; posting after effective end remains enforced in JournalEntry.clean().
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.utils import timezone


def effective_project_end(project) -> date | None:
    eff = getattr(project, "effective_end_date", None)
    if callable(eff):
        return eff()
    return getattr(project, "end_date", None)


def project_end_alert_state(project, today: date | None = None) -> str | None:
    """
    Calendar alert for list/UI: ending_soon (<=5 days), on_end, expired (past effective end).
    None if no end date, project is closed/completed, or outside window.
    """
    from tenant_grants.models import Project

    today = today or timezone.now().date()
    if project.status in (Project.Status.CLOSED, Project.Status.COMPLETED):
        return None
    eff = effective_project_end(project)
    if not eff:
        return None
    days = (eff - today).days
    if days > 5:
        return None
    if days > 0:
        return "ending_soon"
    if days == 0:
        return "on_end"
    return "expired"


def user_can_manage_project_closure_or_extension(tenant_user, project, tenant_db: str) -> bool:
    """Only tenant admin, finance manage, or assigned project manager may close or extend."""
    if not tenant_user:
        return False
    if getattr(tenant_user, "is_tenant_admin", False):
        return True
    from rbac.models import user_has_permission

    if user_has_permission(tenant_user, "module:finance.manage", using=tenant_db):
        return True
    pm_id = getattr(project, "project_manager_id", None)
    if pm_id and pm_id == tenant_user.pk:
        return True
    return False


def project_closure_blockers(project, tenant_db: str) -> list[str]:
    """
    Reasons a project must not be closed yet (receivables, unposted activity, budget lines).
    """
    from tenant_finance.models import JournalEntry
    from tenant_grants.models import Grant, ProjectBudgetLine

    msgs: list[str] = []

    grant_ids = list(
        Grant.objects.using(tenant_db).filter(project_id=project.pk).values_list("pk", flat=True)
    )
    if grant_ids:
        pending_j = (
            JournalEntry.objects.using(tenant_db)
            .filter(grant_id__in=grant_ids)
            .exclude(status=JournalEntry.Status.POSTED)
            .count()
        )
        if pending_j:
            msgs.append(
                f"{pending_j} journal entr(y/ies) for grants on this project are not posted yet."
            )

        open_rec = False
        for g in Grant.objects.using(tenant_db).filter(pk__in=grant_ids, status=Grant.Status.ACTIVE):
            elig = g.eligible_receivable_amount or Decimal("0")
            if elig > 0:
                open_rec = True
                break
        if open_rec:
            msgs.append(
                "Receivables are still open: active grants on this project have eligible receivable balances."
            )

    line_remain = (
        ProjectBudgetLine.objects.using(tenant_db)
        .filter(project_budget__project_id=project.pk)
        .exclude(remaining_amount=Decimal("0"))
    )
    if line_remain.filter(remaining_amount__gt=Decimal("0.01")).exists():
        msgs.append(
            "Project budget lines still show remaining balances; finalize or reallocate before closure."
        )

    return msgs
