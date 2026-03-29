from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tenant_finance.models import FiscalYear


@dataclass(frozen=True)
class PeriodMatch:
    period_id: int
    fiscal_year_id: int
    status: str
    name: str


def _normalize(s: str) -> str:
    return (s or "").strip().lower()


def _user_display(user) -> str:
    return (getattr(user, "full_name", "") or "").strip() or getattr(user, "email", "") or ""


def create_fiscal_year_with_monthly_periods(
    *,
    using: str,
    name: str,
    start_date: date,
    end_date: date,
    created_by=None,
) -> "FiscalYear":
    """
    Create a fiscal year and monthly accounting periods (up to 12), all status OPEN.

    ``period_type`` is implicitly monthly; one period per calendar month within the FY range.
    """
    from calendar import monthrange

    from django.db import transaction

    from tenant_finance.models import FiscalPeriod, FiscalYear

    with transaction.atomic(using=using):
        fy = FiscalYear.objects.using(using).create(
            name=name,
            start_date=start_date,
            end_date=end_date,
            status=FiscalYear.Status.OPEN,
            created_by=created_by,
        )
        current = start_date
        period_no = 1
        while current <= end_date and period_no <= 12:
            y, m = current.year, current.month
            last_day = monthrange(y, m)[1]
            month_end = date(y, m, last_day)
            period_end = min(month_end, end_date)
            FiscalPeriod.objects.using(using).create(
                fiscal_year=fy,
                period_number=period_no,
                name=current.strftime("%b %Y"),
                period_name=current.strftime("%B %Y"),
                start_date=current,
                end_date=period_end,
                status=FiscalPeriod.Status.OPEN,
            )
            if period_end >= end_date:
                break
            if m == 12:
                current = date(y + 1, 1, 1)
            else:
                current = date(y, m + 1, 1)
            period_no += 1
        return fy


def get_period_for_date(*, using: str, dt: date):
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
    return p


def assert_can_post(*, using: str, dt: date, user=None) -> PeriodMatch:
    """
    Enforce:
    - date must fall within a period range
    - fiscal year must not be closed
    - hard-closed periods block posting
    - soft-closed periods allow limited posting by roles
    """
    from tenant_finance.models import FiscalYear

    p = get_period_for_date(using=using, dt=dt)
    fy = p.fiscal_year
    if fy and (fy.is_closed or fy.status == FiscalYear.Status.CLOSED):
        raise ValueError(f"Fiscal year is closed ({fy.name}).")
    if not p.is_posting_allowed(user=user):
        if _normalize(p.status) == "soft_closed":
            raise ValueError(
                "Accounting period is soft closed. Reopen the period (Financial Setup) before posting."
            )
        raise ValueError("Accounting period is hard closed; posting is not allowed.")
    return PeriodMatch(
        period_id=p.id,
        fiscal_year_id=p.fiscal_year_id,
        status=p.status,
        name=p.name or p.period_name or str(p),
    )


def _prior_open_exists(*, using: str, period) -> bool:
    from tenant_finance.models import FiscalPeriod

    return FiscalPeriod.objects.using(using).filter(
        fiscal_year_id=period.fiscal_year_id,
        period_number__lt=period.period_number,
        status=FiscalPeriod.Status.OPEN,
    ).exists()


def close_period(*, using: str, period_id: int, close_type: str, user=None, reason: str = ""):
    """
    Enforce sequential closing:
    - you cannot close period N if any prior period in same fiscal year is still OPEN.
    close_type: "soft" or "hard"
    """
    from django.db import transaction
    from django.utils import timezone

    from tenant_finance.models import AuditLog, FiscalPeriod, PeriodActionLog

    ct = _normalize(close_type)
    if ct not in ("soft", "hard"):
        raise ValueError("Invalid close type.")
    if not (reason or "").strip():
        raise ValueError("Reason is required to close a period.")

    with transaction.atomic(using=using):
        p = FiscalPeriod.objects.using(using).select_for_update().select_related("fiscal_year").get(pk=period_id)
        if p.fiscal_year and (p.fiscal_year.is_closed or p.fiscal_year.status == p.fiscal_year.Status.CLOSED):
            raise ValueError("Cannot close periods in a closed fiscal year.")
        if _prior_open_exists(using=using, period=p):
            raise ValueError("Sequential closing enforced: close earlier open periods first.")

        from_status = p.status
        if ct == "soft":
            p.status = FiscalPeriod.Status.SOFT_CLOSED
            p.is_closed = False
        else:
            p.status = FiscalPeriod.Status.HARD_CLOSED
            p.is_closed = True
        p.closed_by = user
        p.closed_at = timezone.now()
        p.closed_reason = (reason or "").strip()
        p.save(using=using, update_fields=["status", "is_closed", "closed_by", "closed_at", "closed_reason"])

        PeriodActionLog.objects.using(using).create(
            period=p,
            fiscal_year=p.fiscal_year,
            action=PeriodActionLog.Action.SOFT_CLOSE if ct == "soft" else PeriodActionLog.Action.HARD_CLOSE,
            from_status=from_status,
            to_status=p.status,
            reason=p.closed_reason,
            user=user,
        )
        AuditLog.objects.using(using).create(
            model_name="fiscalperiod",
            object_id=p.id,
            action=AuditLog.Action.UPDATE,
            user_id=getattr(user, "id", None),
            username=_user_display(user),
            summary=f"Accounting period {('soft' if ct=='soft' else 'hard')} closed: {p.fiscal_year.name} P{p.period_number}",
            new_data={"status": p.status, "reason": p.closed_reason},
        )


def reopen_period(*, using: str, period_id: int, user=None, reason: str = ""):
    from django.db import transaction
    from django.utils import timezone

    from tenant_finance.models import AuditLog, FiscalPeriod, PeriodActionLog, PeriodControlSetting

    if not (reason or "").strip():
        raise ValueError("Reason is required to reopen a period.")

    setting = PeriodControlSetting.get_solo(using=using)
    if not setting.user_can_reopen(user):
        raise ValueError("You are not authorized to reopen accounting periods.")

    with transaction.atomic(using=using):
        p = FiscalPeriod.objects.using(using).select_for_update().select_related("fiscal_year").get(pk=period_id)
        if p.fiscal_year and (p.fiscal_year.is_closed or p.fiscal_year.status == p.fiscal_year.Status.CLOSED):
            raise ValueError("Cannot reopen periods in a closed fiscal year.")
        if p.status == FiscalPeriod.Status.HARD_CLOSED:
            raise ValueError("Cannot reopen a hard-closed period.")
        if p.status != FiscalPeriod.Status.SOFT_CLOSED:
            raise ValueError("Only soft-closed periods can be reopened.")

        from_status = p.status
        p.status = FiscalPeriod.Status.OPEN
        p.is_closed = False
        p.reopened_by = user
        p.reopened_at = timezone.now()
        p.reopened_reason = (reason or "").strip()
        # Do not erase close info; keep it for audit. Only clear is_closed/status.
        p.save(using=using, update_fields=["status", "is_closed", "reopened_by", "reopened_at", "reopened_reason"])

        PeriodActionLog.objects.using(using).create(
            period=p,
            fiscal_year=p.fiscal_year,
            action=PeriodActionLog.Action.REOPEN,
            from_status=from_status,
            to_status=p.status,
            reason=p.reopened_reason,
            user=user,
        )
        AuditLog.objects.using(using).create(
            model_name="fiscalperiod",
            object_id=p.id,
            action=AuditLog.Action.UPDATE,
            user_id=getattr(user, "id", None),
            username=_user_display(user),
            summary=f"Accounting period reopened: {p.fiscal_year.name} P{p.period_number}",
            new_data={"status": p.status, "reason": p.reopened_reason},
        )

