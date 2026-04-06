"""Subscription plan list helpers (tenant assignment counts use Tenant.plan text match)."""
from __future__ import annotations

from typing import Any

from django.db.models import Q, QuerySet

from tenants.models import SubscriptionPlan, Tenant


def tenant_count_for_plan(plan: SubscriptionPlan) -> int:
    """How many tenants reference this plan by code or name (free-text Tenant.plan)."""
    return Tenant.objects.filter(
        Q(plan__iexact=plan.code) | Q(plan__iexact=plan.name)
    ).count()


def batch_tenant_counts_for_plans(plans: list[SubscriptionPlan]) -> dict[int, int]:
    """Single pass over tenants; counts assignments per plan id (code or name match)."""
    if not plans:
        return {}
    result = {p.id: 0 for p in plans}
    rows = [(p.id, p.code.lower(), (p.name or "").lower()) for p in plans]
    for t in Tenant.objects.exclude(plan="").only("plan"):
        pl = (t.plan or "").strip().lower()
        if not pl:
            continue
        for pid, code, name in rows:
            if pl == code or (name and pl == name):
                result[pid] += 1
                break
    return result


def annotate_plans_with_tenant_counts(plans: list[SubscriptionPlan]) -> None:
    m = batch_tenant_counts_for_plans(plans)
    for p in plans:
        p.assigned_tenant_count = m.get(p.id, 0)


def plan_kpis(qs: QuerySet[SubscriptionPlan]) -> dict[str, Any]:
    total = qs.count()
    active = qs.filter(is_active=True, is_draft=False, is_archived=False).count()
    draft = qs.filter(is_draft=True, is_archived=False).count()
    inactive = qs.filter(is_active=False, is_draft=False, is_archived=False).count()
    draft_inactive = draft + inactive
    public_plans = qs.filter(visibility=SubscriptionPlan.Visibility.PUBLIC, is_archived=False).count()
    trial_enabled = qs.filter(trial_enabled=True, is_archived=False).count()

    all_plans = list(SubscriptionPlan.objects.all())
    counts = batch_tenant_counts_for_plans(all_plans)
    assigned = sum(1 for c in counts.values() if c > 0)

    return {
        "total": total,
        "active": active,
        "draft": draft,
        "inactive": inactive,
        "draft_inactive": draft_inactive,
        "public": public_plans,
        "assigned": assigned,
        "trial_enabled": trial_enabled,
    }


def apply_plan_filters(
    qs: QuerySet[SubscriptionPlan],
    *,
    q: str,
    status_key: str,
    billing_cycle: str,
    visibility: str,
    trial: str,
    module_id: str,
) -> QuerySet[SubscriptionPlan]:
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(description__icontains=q))
    if status_key != "archived":
        if status_key in ("", "all"):
            qs = qs.filter(is_archived=False)
    if status_key == "active":
        qs = qs.filter(is_active=True, is_draft=False, is_archived=False)
    elif status_key == "draft":
        qs = qs.filter(is_draft=True, is_archived=False)
    elif status_key == "inactive":
        qs = qs.filter(is_active=False, is_draft=False, is_archived=False)
    elif status_key == "archived":
        qs = qs.filter(is_archived=True)
    if billing_cycle and billing_cycle != "all":
        qs = qs.filter(billing_cycle=billing_cycle)
    if visibility and visibility != "all":
        qs = qs.filter(visibility=visibility)
    if trial == "yes":
        qs = qs.filter(trial_enabled=True)
    elif trial == "no":
        qs = qs.filter(trial_enabled=False)
    if module_id.isdigit():
        qs = qs.filter(included_modules__id=int(module_id)).distinct()
    return qs


def plan_status_display(plan: SubscriptionPlan) -> str:
    if plan.is_archived:
        return "Archived"
    if plan.is_draft:
        return "Draft"
    if plan.is_active:
        return "Active"
    return "Inactive"
