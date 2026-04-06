"""
Tenant subscription presentation and query helpers for the Platform Console.

The control plane stores subscription-related fields on ``Tenant`` (plan, status,
subscription_expiry, is_active). There is no separate subscription row per tenant yet;
this module treats each tenant as one subscription record for admin UI purposes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from django.db.models import Q, QuerySet
from django.utils import timezone

from tenants.models import Tenant


def _today() -> date:
    return timezone.now().date()


def subscription_expired_by_date(tenant: Tenant) -> bool:
    if tenant.subscription_expiry and tenant.subscription_expiry < _today():
        return True
    return False


def subscription_state_key(tenant: Tenant) -> str:
    """
    Coarse UI bucket for filters and badges.
    active | trial | pending | expired | suspended | draft | failed | unknown
    """
    st = tenant.status
    if st == Tenant.Status.DRAFT:
        return "draft"
    if st == Tenant.Status.FAILED:
        return "failed"
    if st == Tenant.Status.PENDING:
        return "pending"
    if not tenant.is_active:
        return "suspended"
    if st == Tenant.Status.EXPIRED or subscription_expired_by_date(tenant):
        return "expired"
    if st == Tenant.Status.TRIAL:
        return "trial"
    if st == Tenant.Status.SUSPENDED:
        return "suspended"
    if st == Tenant.Status.ACTIVE and tenant.is_active:
        return "active"
    return "unknown"


def has_plan_assigned(tenant: Tenant) -> bool:
    return bool((tenant.plan or "").strip())


def subscription_status_filter_q(key: str) -> Q | None:
    """Return a Q object for subscription list filter, or None for 'all'."""
    today = _today()
    if key in ("", "all"):
        return None
    if key == "active":
        return Q(status=Tenant.Status.ACTIVE, is_active=True) & (
            Q(subscription_expiry__isnull=True) | Q(subscription_expiry__gte=today)
        )
    if key == "trial":
        return Q(status=Tenant.Status.TRIAL)
    if key == "pending":
        return Q(status=Tenant.Status.PENDING)
    if key == "expired":
        return Q(status=Tenant.Status.EXPIRED) | Q(subscription_expiry__lt=today)
    if key == "suspended":
        return Q(status=Tenant.Status.SUSPENDED) | Q(is_active=False)
    if key == "draft":
        return Q(status=Tenant.Status.DRAFT)
    if key == "failed":
        return Q(status=Tenant.Status.FAILED)
    if key == "no_plan":
        return Q(plan__exact="")
    return None


def subscription_kpis(qs: QuerySet[Tenant]) -> dict[str, Any]:
    today = _today()
    total = qs.count()
    active = qs.filter(status=Tenant.Status.ACTIVE, is_active=True).filter(
        Q(subscription_expiry__isnull=True) | Q(subscription_expiry__gte=today)
    ).count()
    trial = qs.filter(status=Tenant.Status.TRIAL).count()
    pending = qs.filter(status=Tenant.Status.PENDING).count()
    expired = qs.filter(Q(status=Tenant.Status.EXPIRED) | Q(subscription_expiry__lt=today)).count()
    suspended = qs.filter(Q(status=Tenant.Status.SUSPENDED) | Q(is_active=False)).count()
    return {
        "total": total,
        "active": active,
        "trial": trial,
        "pending": pending,
        "expired": expired,
        "suspended": suspended,
        "mrr_cents": None,
        "mrr_currency": "USD",
        "mrr_available": False,
    }


@dataclass
class SubscriptionRow:
    tenant: Tenant
    state_key: str
    trial_display: str
    plan_display: str
    modules_short: str
    amount_display: str
    billing_cycle_display: str
    auto_renew_display: str
    start_date: date | None
    expiry_date: date | None


def build_subscription_row(tenant: Tenant) -> SubscriptionRow:
    mods = list(tenant.modules.all())
    codes = [m.code for m in mods[:12]]
    modules_short = ", ".join(codes) if codes else "—"
    if len(mods) > 12:
        modules_short += "…"

    st_key = subscription_state_key(tenant)
    trial_yes = tenant.status == Tenant.Status.TRIAL
    return SubscriptionRow(
        tenant=tenant,
        state_key=st_key,
        trial_display="Yes" if trial_yes else "No",
        plan_display=(tenant.plan or "").strip() or "—",
        modules_short=modules_short,
        amount_display="—",
        billing_cycle_display="—",
        auto_renew_display="—",
        start_date=tenant.created_at.date() if tenant.created_at else None,
        expiry_date=tenant.subscription_expiry,
    )


def apply_subscription_filters(
    qs: QuerySet[Tenant],
    *,
    q: str,
    status_key: str,
    plan: str,
    module_id: str,
    start_from: date | None,
    start_to: date | None,
    expiry_from: date | None,
    expiry_to: date | None,
    billing_cycle: str,
) -> tuple[QuerySet[Tenant], bool]:
    """
    Returns (queryset, billing_cycle_note_shown).
    billing_cycle_note_shown is True when user chose a non-any cycle but DB has no field yet.
    """
    note = False
    if q:
        qs = qs.filter(
            Q(name__icontains=q) | Q(slug__icontains=q) | Q(domain__icontains=q)
        )
    sf = subscription_status_filter_q(status_key)
    if sf is not None:
        qs = qs.filter(sf)
    if plan:
        qs = qs.filter(
            Q(plan__iexact=plan) | Q(plan__icontains=plan)
        )
    if module_id.isdigit():
        qs = qs.filter(modules__id=int(module_id)).distinct()
    if start_from:
        qs = qs.filter(created_at__date__gte=start_from)
    if start_to:
        qs = qs.filter(created_at__date__lte=start_to)
    if expiry_from:
        qs = qs.filter(subscription_expiry__gte=expiry_from)
    if expiry_to:
        qs = qs.filter(subscription_expiry__lte=expiry_to)

    bc = (billing_cycle or "any").strip().lower()
    if bc not in ("", "any"):
        note = True

    return qs, note
