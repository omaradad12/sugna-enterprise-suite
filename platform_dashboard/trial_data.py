"""
Trials management helpers for the Platform Console.

Trial state is derived from ``Tenant.status == TRIAL`` and ``subscription_expiry``,
with optional ``trial_started_at`` / ``trial_converted_at`` for clearer history.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from django.db.models import Q, QuerySet
from django.utils import timezone

from tenants.models import Tenant


def trial_today() -> date:
    return timezone.now().date()


def trial_start_date(tenant: Tenant) -> date | None:
    if getattr(tenant, "trial_started_at", None):
        return tenant.trial_started_at
    if tenant.created_at:
        return tenant.created_at.date()
    return None


def days_remaining_trial(tenant: Tenant, today: date | None = None) -> int | None:
    """Days until trial expiry; negative if past. None if no expiry set."""
    today = today or trial_today()
    if getattr(tenant, "trial_converted_at", None):
        return None
    exp = tenant.subscription_expiry
    if not exp:
        return None
    return (exp - today).days


def trial_row_alert(tenant: Tenant, today: date | None = None) -> str:
    """
    Visual bucket for row styling: ok | expiring_soon | expired | converted | suspended
    """
    today = today or trial_today()
    if getattr(tenant, "trial_converted_at", None):
        return "converted"
    if not tenant.is_active and tenant.status == Tenant.Status.TRIAL:
        return "suspended"
    if tenant.status != Tenant.Status.TRIAL:
        return "ok"
    exp = tenant.subscription_expiry
    if exp and exp < today:
        return "expired"
    if exp and today <= exp <= today + timedelta(days=7):
        return "expiring_soon"
    return "ok"


def trial_status_label(tenant: Tenant, today: date | None = None) -> str:
    today = today or trial_today()
    if getattr(tenant, "trial_converted_at", None):
        return "Converted"
    if not tenant.is_active and tenant.status == Tenant.Status.TRIAL:
        return "Suspended"
    if tenant.status != Tenant.Status.TRIAL:
        return tenant.get_status_display()
    exp = tenant.subscription_expiry
    if exp and exp < today:
        return "Expired"
    if exp and today <= exp <= today + timedelta(days=7):
        return "Expiring soon"
    return "Active"


def trial_kpis(base: QuerySet[Tenant]) -> dict[str, Any]:
    today = trial_today()
    end7 = today + timedelta(days=7)
    trial_qs = base.filter(status=Tenant.Status.TRIAL)
    total_trials = trial_qs.count()
    active_trials = trial_qs.filter(
        Q(subscription_expiry__isnull=True) | Q(subscription_expiry__gte=today)
    ).count()
    expiring_7 = trial_qs.filter(
        subscription_expiry__gte=today,
        subscription_expiry__lte=end7,
    ).count()
    expired_trials = trial_qs.filter(subscription_expiry__lt=today).count()
    converted = base.filter(trial_converted_at__isnull=False).count()
    ended_without_convert = expired_trials
    conversion_denom = converted + ended_without_convert
    conversion_rate = None
    if conversion_denom > 0:
        conversion_rate = round(100.0 * converted / conversion_denom, 1)
    return {
        "total_trials": total_trials,
        "active_trials": active_trials,
        "expiring_7": expiring_7,
        "expired_trials": expired_trials,
        "converted": converted,
        "conversion_rate": conversion_rate,
        "conversion_rate_available": conversion_denom > 0,
    }


def trial_status_filter_q(key: str, today: date | None = None) -> Q | None:
    today = today or trial_today()
    end7 = today + timedelta(days=7)
    if key in ("", "all"):
        return None
    if key == "active":
        return Q(status=Tenant.Status.TRIAL) & (
            Q(subscription_expiry__isnull=True) | Q(subscription_expiry__gte=today)
        )
    if key == "expired":
        return Q(status=Tenant.Status.TRIAL) & Q(subscription_expiry__lt=today)
    if key == "expiring_soon":
        return Q(status=Tenant.Status.TRIAL) & Q(
            subscription_expiry__gte=today,
            subscription_expiry__lte=end7,
        )
    if key == "converted":
        return Q(trial_converted_at__isnull=False)
    if key == "suspended":
        return Q(status=Tenant.Status.TRIAL, is_active=False)
    return None


def trials_base_queryset() -> QuerySet[Tenant]:
    return Tenant.objects.filter(
        Q(status=Tenant.Status.TRIAL) | Q(trial_converted_at__isnull=False)
    )


def apply_trial_filters(
    qs: QuerySet[Tenant],
    *,
    q: str,
    status_key: str,
    plan: str,
    module_id: str,
    country: str,
    start_from: date | None,
    start_to: date | None,
    expiry_from: date | None,
    expiry_to: date | None,
) -> QuerySet[Tenant]:
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(slug__icontains=q) | Q(domain__icontains=q))
    sf = trial_status_filter_q(status_key)
    if sf is not None:
        qs = qs.filter(sf)
    if plan:
        qs = qs.filter(Q(plan__iexact=plan) | Q(plan__icontains=plan))
    if module_id.isdigit():
        qs = qs.filter(modules__id=int(module_id)).distinct()
    if country:
        qs = qs.filter(country__icontains=country)
    # Trial start range: trial_started_at when set, else date(created_at)
    if start_from:
        qs = qs.filter(
            Q(trial_started_at__gte=start_from)
            | Q(trial_started_at__isnull=True, created_at__date__gte=start_from)
        )
    if start_to:
        qs = qs.filter(
            Q(trial_started_at__lte=start_to)
            | Q(trial_started_at__isnull=True, created_at__date__lte=start_to)
        )
    if expiry_from:
        qs = qs.filter(subscription_expiry__gte=expiry_from)
    if expiry_to:
        qs = qs.filter(subscription_expiry__lte=expiry_to)
    return qs


@dataclass
class TrialRow:
    tenant: Tenant
    trial_start: date | None
    days_remaining: int | None
    status_label: str
    alert: str
    converted: bool
    modules_short: str
    plan_display: str


def build_trial_row(tenant: Tenant) -> TrialRow:
    mods = list(tenant.modules.all())
    codes = [m.code for m in mods[:10]]
    modules_short = ", ".join(codes) if codes else "—"
    if len(mods) > 10:
        modules_short += "…"
    today = trial_today()
    converted = bool(getattr(tenant, "trial_converted_at", None))
    return TrialRow(
        tenant=tenant,
        trial_start=trial_start_date(tenant),
        days_remaining=days_remaining_trial(tenant, today),
        status_label=trial_status_label(tenant, today),
        alert=trial_row_alert(tenant, today),
        converted=converted,
        modules_short=modules_short,
        plan_display=(tenant.plan or "").strip() or "—",
    )
