"""
Project budget vs actual: journal validation and denormalized remaining / actual_cost refresh.
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tenant_finance.models import JournalEntry


def project_has_budget_lines(using: str, project_id: int) -> bool:
    from tenant_grants.models import ProjectBudgetLine

    return (
        ProjectBudgetLine.objects.using(using)
        .filter(project_budget__project_id=project_id)
        .exists()
    )


def validate_journal_entry_expense_budget_dimensions(entry: JournalEntry, using: str) -> list[str]:
    """
    When a grant's project has project budget lines, each expense debit line must tag
    project_budget_line and/or workplan_activity for audit / activity-based reporting.
    """
    from tenant_finance.models import ChartAccount
    from tenant_grants.models import Grant, ProjectBudgetLine

    gid = entry.grant_id
    if not gid:
        return []
    grant = Grant.objects.using(using).filter(pk=gid).select_related("project").first()
    if not grant or not grant.project_id:
        return []
    if not project_has_budget_lines(using, grant.project_id):
        return []
    errs: list[str] = []
    lines = list(entry.lines.using(using).select_related("account"))
    for i, line in enumerate(lines, start=1):
        if line.account.type != ChartAccount.Type.EXPENSE or (line.debit or 0) <= 0:
            continue
        if line.project_budget_line_id or line.workplan_activity_id:
            continue
        errs.append(
            f"Line {i} ({line.account.code}): expense must reference a project budget line "
            "and/or workplan activity (project has a budget structure)."
        )
    return errs


def _project_ids_touched_by_entry(entry: JournalEntry, using: str) -> set[int]:
    from tenant_grants.models import WorkplanActivity

    ids: set[int] = set()
    if entry.grant_id:
        g = entry.grant
        if getattr(g, "project_id", None):
            ids.add(g.project_id)
    for line in entry.lines.using(using).select_related(
        "project_budget_line__project_budget",
        "workplan_activity",
    ):
        if line.project_budget_line_id:
            ids.add(line.project_budget_line.project_budget.project_id)
        if line.workplan_activity_id:
            wa = line.workplan_activity
            pid = getattr(wa, "project_id", None) or (
                wa.grant.project_id if getattr(wa, "grant_id", None) and wa.grant.project_id else None
            )
            if pid:
                ids.add(pid)
    return ids


def refresh_project_budget_and_activity_actuals(
    using: str, *, project_ids: set[int] | None = None, entry: JournalEntry | None = None
) -> None:
    """
    Recompute ProjectBudgetLine.remaining_amount and WorkplanActivity.actual_cost from posted journals.
    """
    from django.db.models import Q, Sum

    from tenant_finance.models import ChartAccount, JournalEntry, JournalLine
    from tenant_grants.models import ProjectBudgetLine, WorkplanActivity

    pbl_ids: set[int] = set()
    wa_ids: set[int] = set()
    if entry is not None:
        for ln in entry.lines.using(using).only(
            "project_budget_line_id", "workplan_activity_id"
        ):
            if ln.project_budget_line_id:
                pbl_ids.add(ln.project_budget_line_id)
            if ln.workplan_activity_id:
                wa_ids.add(ln.workplan_activity_id)
        if project_ids is None and not pbl_ids:
            project_ids = _project_ids_touched_by_entry(entry, using)

    pbl_qs = ProjectBudgetLine.objects.using(using).select_related("project_budget")
    if pbl_ids:
        pbl_qs = pbl_qs.filter(pk__in=pbl_ids)
    elif project_ids:
        pbl_qs = pbl_qs.filter(project_budget__project_id__in=project_ids)
    else:
        pbl_qs = pbl_qs.none()
    for pbl in pbl_qs.iterator(chunk_size=200):
        exp = (
            JournalLine.objects.using(using)
            .filter(
                project_budget_line_id=pbl.pk,
                entry__status=JournalEntry.Status.POSTED,
                account__type=ChartAccount.Type.EXPENSE,
                debit__gt=0,
            )
            .aggregate(s=Sum("debit"))
            .get("s")
            or Decimal("0")
        )
        alloc = pbl.allocated_amount or Decimal("0")
        ProjectBudgetLine.objects.using(using).filter(pk=pbl.pk).update(remaining_amount=alloc - exp)

    wa_qs = WorkplanActivity.objects.using(using)
    if wa_ids:
        wa_qs = wa_qs.filter(pk__in=wa_ids)
    elif project_ids:
        wa_qs = wa_qs.filter(Q(project_id__in=project_ids) | Q(grant__project_id__in=project_ids))
    else:
        wa_qs = wa_qs.none()
    for act in wa_qs.iterator(chunk_size=200):
        exp = (
            JournalLine.objects.using(using)
            .filter(
                workplan_activity_id=act.pk,
                entry__status=JournalEntry.Status.POSTED,
                account__type=ChartAccount.Type.EXPENSE,
                debit__gt=0,
            )
            .aggregate(s=Sum("debit"))
            .get("s")
            or Decimal("0")
        )
        WorkplanActivity.objects.using(using).filter(pk=act.pk).update(actual_cost=exp)
