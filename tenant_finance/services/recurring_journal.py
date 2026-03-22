"""
Recurring journal templates: validation, balanced lines, next run date (NGO / fund accounting).
"""
from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal
from typing import Any

from django.db import transaction


def add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    last_day = calendar.monthrange(y, m)[1]
    day = min(d.day, last_day)
    return date(y, m, day)


def compute_next_run_after(
    *,
    last_run: date,
    frequency: str,
) -> date:
    from tenant_finance.models import RecurringJournal

    if frequency == RecurringJournal.Frequency.MONTHLY:
        return add_months(last_run, 1)
    if frequency == RecurringJournal.Frequency.QUARTERLY:
        return add_months(last_run, 3)
    if frequency == RecurringJournal.Frequency.YEARLY:
        return add_months(last_run, 12)
    return add_months(last_run, 1)


def initial_next_run_date(*, start_date: date) -> date:
    """First scheduled run is on start date."""
    return start_date


def parse_line_rows(post_data) -> list[dict[str, Any]]:
    """Parse indexed line_* fields from POST (expects line_count)."""
    try:
        n = int(post_data.get("line_count") or "0")
    except (TypeError, ValueError):
        n = 0
    lines: list[dict[str, Any]] = []
    for i in range(max(n, 0)):
        acc = post_data.get(f"line_account_{i}")
        if acc is None:
            continue
        acc_s = (acc or "").strip()
        dr_s = (post_data.get(f"line_debit_{i}") or "").strip()
        cr_s = (post_data.get(f"line_credit_{i}") or "").strip()
        if not acc_s and not dr_s and not cr_s:
            continue
        lines.append(
            {
                "account_id": acc_s,
                "grant_id": (post_data.get(f"line_grant_{i}") or "").strip(),
                "description": (post_data.get(f"line_desc_{i}") or "").strip(),
                "debit": dr_s,
                "credit": cr_s,
            }
        )
    return lines


def validate_recurring_journal_payload(
    *,
    tenant_db: str,
    name: str,
    frequency: str,
    start_date: date | None,
    status: str,
    lines: list[dict[str, Any]],
    end_date: date | None = None,
):
    """
    Returns (normalized_lines, None) or (None, error_message).
    """
    from tenant_finance.models import ChartAccount, RecurringJournal
    from tenant_grants.models import Grant, Project

    if not (name or "").strip():
        return None, "Template name is required."
    if frequency not in {c[0] for c in RecurringJournal.Frequency.choices}:
        return None, "Frequency is required."
    if not start_date:
        return None, "Start date is required."
    if status not in {c[0] for c in RecurringJournal.Status.choices}:
        return None, "Status is invalid."

    from tenant_finance.services.interfund_validation import assert_open_accounting_period_for_date

    try:
        assert_open_accounting_period_for_date(start_date, tenant_db, user=None)
    except ValueError as exc:
        return None, str(exc)

    if end_date and end_date < start_date:
        return None, "End date must be on or after start date."

    if len(lines) < 2:
        return None, "Add at least two journal lines."

    total_dr = Decimal("0")
    total_cr = Decimal("0")
    normalized: list[dict[str, Any]] = []

    for row in lines:
        aid = row.get("account_id") or ""
        if not str(aid).isdigit():
            return None, "Each line must have an account."
        account = (
            ChartAccount.objects.using(tenant_db)
            .filter(pk=int(aid))
            .first()
        )
        if not account:
            return None, "Invalid account on a line."
        if not account.is_active:
            return None, f"Account {account.code} is inactive."

        try:
            dr = Decimal(str(row.get("debit") or "0").strip() or "0")
            cr = Decimal(str(row.get("credit") or "0").strip() or "0")
        except Exception:
            return None, "Debit and credit must be valid numbers."

        if dr < 0 or cr < 0:
            return None, "Amounts cannot be negative."
        if dr > 0 and cr > 0:
            return None, "Each line must have either debit or credit, not both."
        if dr == 0 and cr == 0:
            return None, "Each line must have a debit or a credit amount."
        if dr > 0 and cr == 0:
            total_dr += dr
        else:
            total_cr += cr

        grant = None
        gid = row.get("grant_id") or ""
        if str(gid).strip().isdigit():
            grant = (
                Grant.objects.using(tenant_db)
                .filter(pk=int(gid))
                .select_related("project")
                .first()
            )
            if not grant:
                return None, "Invalid project / grant on a line."
            if grant.status != Grant.Status.ACTIVE:
                return None, f"Grant {grant.code} is not active."
            if grant.project_id and grant.project:
                if grant.project.status != Project.Status.ACTIVE:
                    return None, f"Project for grant {grant.code} must be active."
                if not getattr(grant.project, "is_active", True):
                    return None, f"Project for grant {grant.code} is not available."

        normalized.append(
            {
                "account_id": int(aid),
                "grant_id": int(gid) if str(gid).strip().isdigit() else None,
                "description": (row.get("description") or "")[:255],
                "debit": dr if dr > 0 else Decimal("0"),
                "credit": cr if cr > 0 else Decimal("0"),
            }
        )

    if total_dr != total_cr:
        return None, f"Total debit ({total_dr}) must equal total credit ({total_cr})."

    return normalized, None


def save_recurring_template(
    *,
    tenant_db: str,
    journal_id: int | None,
    name: str,
    reference_prefix: str,
    frequency: str,
    start_date: date,
    end_date: date | None,
    description: str,
    status: str,
    raw_lines: list[dict[str, Any]],
):
    from tenant_finance.models import RecurringJournal, RecurringJournalLine

    normalized, err = validate_recurring_journal_payload(
        tenant_db=tenant_db,
        name=name,
        frequency=frequency,
        start_date=start_date,
        status=status,
        lines=raw_lines,
        end_date=end_date,
    )
    if err:
        return None, err
    assert normalized is not None

    with transaction.atomic(using=tenant_db):
        if journal_id:
            rj = (
                RecurringJournal.objects.using(tenant_db)
                .filter(pk=journal_id)
                .first()
            )
            if not rj:
                return None, "Template not found."
        else:
            rj = RecurringJournal()

        rj.name = name.strip()
        rj.reference_prefix = (reference_prefix or "").strip()[:30]
        rj.description = (description or "").strip()
        rj.frequency = frequency
        rj.start_date = start_date
        rj.end_date = end_date
        rj.status = status
        rj.next_run_date = initial_next_run_date(start_date=start_date)
        if end_date and rj.next_run_date and rj.next_run_date > end_date:
            rj.status = RecurringJournal.Status.COMPLETED
        rj.save(using=tenant_db)

        RecurringJournalLine.objects.using(tenant_db).filter(
            recurring_journal=rj
        ).delete()
        for order, row in enumerate(normalized):
            RecurringJournalLine.objects.using(tenant_db).create(
                recurring_journal=rj,
                account_id=row["account_id"],
                grant_id=row.get("grant_id"),
                description=row.get("description") or "",
                debit=row["debit"],
                credit=row["credit"],
                display_order=order,
            )

    return rj, None
