"""Platform Console — subscription plans CRUD and actions."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from tenants.models import Module, SubscriptionPlan, Tenant

from .plan_data import (
    annotate_plans_with_tenant_counts,
    apply_plan_filters,
    plan_kpis,
    plan_status_display,
    tenant_count_for_plan,
)
from .plan_forms import SubscriptionPlanForm


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def plans_list_view(request):
    if request.method == "POST":
        return plan_action_view(request)

    q = (request.GET.get("q") or "").strip()
    status_key = (request.GET.get("status") or "all").strip()
    billing_cycle = (request.GET.get("billing_cycle") or "all").strip()
    visibility = (request.GET.get("visibility") or "all").strip()
    trial = (request.GET.get("trial") or "all").strip()
    module_filter = (request.GET.get("module") or "").strip()
    sort = (request.GET.get("sort") or "sort_order").strip()
    per_page = max(10, min(100, int(request.GET.get("per_page", 25))))
    page_num = max(1, int(request.GET.get("page", 1)))

    base = SubscriptionPlan.objects.prefetch_related("included_modules").all()
    kpis = plan_kpis(SubscriptionPlan.objects.all())

    qs = apply_plan_filters(
        base,
        q=q,
        status_key=status_key,
        billing_cycle=billing_cycle,
        visibility=visibility,
        trial=trial,
        module_id=module_filter,
    )

    allowed_sort = {
        "sort_order",
        "-sort_order",
        "name",
        "-name",
        "code",
        "-code",
        "price",
        "-price",
        "updated_at",
        "-updated_at",
    }
    if sort in allowed_sort:
        qs = qs.order_by(sort)
    else:
        qs = qs.order_by("sort_order", "code")

    paginator = Paginator(qs, per_page)
    page = paginator.get_page(page_num)
    plans_list = list(page.object_list)
    annotate_plans_with_tenant_counts(plans_list)
    for p in plans_list:
        p.status_display = plan_status_display(p)

    modules = Module.objects.filter(is_active=True).order_by("sort_order", "code")
    module_filter_id = int(module_filter) if module_filter.isdigit() else None

    empty = not SubscriptionPlan.objects.exists()

    context = {
        "plans": plans_list,
        "page": page,
        "kpis": kpis,
        "filters": {
            "q": q,
            "status": status_key,
            "billing_cycle": billing_cycle,
            "visibility": visibility,
            "trial": trial,
            "module": module_filter,
            "sort": sort,
            "per_page": per_page,
        },
        "modules": modules,
        "module_filter_id": module_filter_id,
        "plans_empty": empty,
    }
    return render(request, "platform_dashboard/plans_list.html", context)


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
@require_POST
def plan_action_view(request):
    action = (request.POST.get("action") or "").strip()
    pid = request.POST.get("plan_id")
    next_url = (request.POST.get("next") or "").strip()
    dest = redirect("platform_dashboard:plans_list")
    if next_url.startswith("/platform/"):
        dest = HttpResponseRedirect(next_url)

    if not pid or not pid.isdigit():
        messages.error(request, "Invalid request.")
        return dest

    with transaction.atomic():
        plan = get_object_or_404(SubscriptionPlan.objects.select_for_update(), pk=int(pid))

        if action == "activate":
            plan.is_active = True
            plan.is_draft = False
            plan.is_archived = False
            plan.save()
            messages.success(request, f"Plan «{plan.name}» is active.")
        elif action == "deactivate":
            plan.is_active = False
            plan.save()
            messages.warning(request, f"Plan «{plan.name}» deactivated.")
        elif action == "archive":
            plan.is_archived = True
            plan.is_active = False
            plan.save()
            messages.info(request, f"Plan «{plan.name}» archived.")
        elif action == "unarchive":
            plan.is_archived = False
            plan.save()
            messages.success(request, f"Plan «{plan.name}» restored from archive.")
        else:
            messages.error(request, "Unknown action.")
            return dest

    return dest


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def plan_detail_view(request, pk):
    plan = get_object_or_404(
        SubscriptionPlan.objects.prefetch_related("included_modules"),
        pk=pk,
    )
    plan.assigned_tenant_count = tenant_count_for_plan(plan)
    assigned_tenants = list(
        Tenant.objects.filter(Q(plan__iexact=plan.code) | Q(plan__iexact=plan.name)).order_by("name")[:500]
    )
    context = {
        "plan": plan,
        "assigned_tenants": assigned_tenants,
        "status_display": plan_status_display(plan),
    }
    return render(request, "platform_dashboard/plan_detail.html", context)


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def plan_create_view(request):
    if request.method == "POST":
        form = SubscriptionPlanForm(request.POST)
        if form.is_valid():
            plan = form.save()
            messages.success(request, f"Created plan «{plan.name}».")
            return redirect("platform_dashboard:plan_detail", pk=plan.pk)
    else:
        form = SubscriptionPlanForm(initial={"currency": "USD", "sort_order": 0})
    return render(
        request,
        "platform_dashboard/plan_form.html",
        {"form": form, "mode": "create", "plan": None},
    )


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def plan_edit_view(request, pk):
    plan = get_object_or_404(SubscriptionPlan.objects.prefetch_related("included_modules"), pk=pk)
    if request.method == "POST":
        form = SubscriptionPlanForm(request.POST, instance=plan)
        if form.is_valid():
            form.save()
            messages.success(request, f"Saved plan «{plan.name}».")
            return redirect("platform_dashboard:plan_detail", pk=plan.pk)
    else:
        form = SubscriptionPlanForm(instance=plan)
    return render(
        request,
        "platform_dashboard/plan_form.html",
        {"form": form, "mode": "edit", "plan": plan},
    )


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
@require_POST
def plan_duplicate_view(request, pk):
    src = get_object_or_404(SubscriptionPlan.objects.prefetch_related("included_modules"), pk=pk)
    base_code = f"{src.code}-copy"
    new_code = base_code
    n = 1
    while SubscriptionPlan.objects.filter(code=new_code).exists():
        new_code = f"{src.code}-copy-{n}"
        n += 1

    plan = SubscriptionPlan.objects.create(
        code=new_code,
        name=f"{src.name} (copy)",
        description=src.description,
        is_active=False,
        is_draft=True,
        is_archived=False,
        sort_order=src.sort_order,
        price=src.price,
        currency=src.currency,
        billing_cycle=src.billing_cycle,
        trial_enabled=src.trial_enabled,
        trial_duration_days=src.trial_duration_days,
        visibility=src.visibility,
        max_users=src.max_users,
        max_storage_mb=src.max_storage_mb,
        max_organizations=src.max_organizations,
    )
    plan.included_modules.set(src.included_modules.all())
    messages.success(request, f"Duplicated as «{plan.name}». Review and activate when ready.")
    return redirect("platform_dashboard:plan_edit", pk=plan.pk)
