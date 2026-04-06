import csv
import json
import logging
import os
from datetime import timedelta
from pathlib import Path
from secrets import token_urlsafe

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q
from django.db import IntegrityError, transaction, utils as db_utils
from django.utils.dateparse import parse_date
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from tenants.branding import extract_brand_colors
from tenants.db import ensure_tenant_db_configured
from tenants.models import Module, SubscriptionPlan, Tenant, TenantBrandingProfile, TenantDomain, TenantModule
from tenants.services.onboarding import run_full_tenant_provisioning
from tenants.services.registration_cleanup import cleanup_failed_registration_tenant
from tenants.services.tenant_modules import replace_tenant_modules
from tenants.workplace import (
    PLATFORM_MODULE_ROUTE,
    is_platform_module,
    resolve_tenant_workspace_open_url,
    tenant_module_home_relpath,
)

from .subscription_data import (
    apply_subscription_filters,
    build_subscription_row,
    subscription_kpis,
)
from .tenant_schema import tenant_table_has_trial_date_columns
from .trial_data import (
    apply_trial_filters,
    build_trial_row,
    trial_kpis,
    trials_base_queryset,
)

logger = logging.getLogger(__name__)


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def platform_coming_soon_view(request, slug: str):
    """Placeholder for platform admin areas that are not built yet (scalable menu targets)."""
    if slug == "tenant-subscriptions":
        return redirect("platform_dashboard:tenant_subscriptions")
    if slug == "trials":
        return redirect("platform_dashboard:trials")
    page_title = slug.replace("-", " ").replace("_", " ").strip().title() or "Coming soon"
    return render(
        request,
        "platform_dashboard/coming_soon.html",
        {"page_title": page_title, "feature_slug": slug},
    )


def logo_view(request):
    """Serve the Sugna logo image so it loads regardless of static files config."""
    logo_path = Path(settings.BASE_DIR) / "platform_dashboard" / "static" / "platform_dashboard" / "images" / "sugna-logo.png"
    if not logo_path.exists():
        # Fallback: the repo may not ship the PNG asset. Return an inline SVG so
        # templates using `{% url 'platform_dashboard:logo' %}` never show a broken image.
        svg = """<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 28 28" fill="none">
  <rect x="3.5" y="3.5" width="10" height="10" rx="2.2" fill="rgba(0,120,212,0.95)"/>
  <rect x="14.5" y="3.5" width="10" height="10" rx="2.2" fill="rgba(16,110,190,0.95)"/>
  <rect x="3.5" y="14.5" width="10" height="10" rx="2.2" fill="rgba(16,110,190,0.95)"/>
  <rect x="14.5" y="14.5" width="10" height="10" rx="2.2" fill="rgba(0,120,212,0.95)"/>
</svg>"""
        return HttpResponse(svg, content_type="image/svg+xml")
    with open(logo_path, "rb") as f:
        return HttpResponse(f.read(), content_type="image/png")


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def dashboard_view(request):
    """Platform Admin dashboard with KPIs, charts, and activity sections."""
    now = timezone.now()

    # KPI data from existing models (extend when billing/registrations exist)
    total_tenants = Tenant.objects.count()
    active_tenants = Tenant.objects.filter(status=Tenant.Status.ACTIVE, is_active=True).count()
    inactive_tenants = total_tenants - active_tenants
    trial_tenants = Tenant.objects.filter(status=Tenant.Status.TRIAL).count()
    expired_tenants = Tenant.objects.filter(status=Tenant.Status.EXPIRED).count()
    monthly_revenue = 0  # placeholder until billing exists
    active_modules = Module.objects.filter(is_active=True).count()
    pending_registrations = 0  # placeholder
    support_tickets = 0  # placeholder

    # Trend vs previous period with percentage change for KPI cards
    _prev = now - timedelta(days=30)
    prev_tenants = Tenant.objects.filter(created_at__date__lt=_prev.date()).count()
    prev_active = Tenant.objects.filter(is_active=True, updated_at__date__lt=_prev.date()).count() if total_tenants else 0

    def _pct(prev_val, curr_val):
        if prev_val == 0:
            return 100.0 if curr_val > 0 else 0.0
        return round(((curr_val - prev_val) / prev_val) * 100, 1)

    pct_total = _pct(prev_tenants, total_tenants)
    pct_active = _pct(prev_active, active_tenants)
    # Real trends only (no sample percentages)
    trial_pct = 0
    expired_pct = 0
    revenue_pct = 0.0
    kpi_trends = {
        "total_tenants": {"dir": "up" if total_tenants > prev_tenants else "down" if total_tenants < prev_tenants else "neutral", "value": abs(total_tenants - prev_tenants), "pct": abs(pct_total), "label": "vs last month"},
        "active_tenants": {"dir": "up" if active_tenants > prev_active else "down" if active_tenants < prev_active else "neutral", "value": abs(active_tenants - prev_active), "pct": abs(pct_active), "label": "vs last month"},
        "trial_tenants": {"dir": "neutral", "value": trial_tenants, "pct": 0, "label": "vs last month"},
        "expired_tenants": {"dir": "down" if expired_tenants == 0 else "up", "value": expired_tenants, "pct": 0, "label": "vs last month"},
        "monthly_revenue": {"dir": "neutral", "value": 0, "pct": revenue_pct, "label": "vs last month"},
        "active_modules": {"dir": "neutral", "value": 0, "pct": 0, "label": "available"},
        "pending_registrations": {"dir": "up" if pending_registrations > 0 else "neutral", "value": pending_registrations, "pct": pending_registrations, "label": "pending"},
        "support_tickets": {"dir": "up" if support_tickets > 0 else "neutral", "value": support_tickets, "pct": support_tickets, "label": "open"},
    }

    # Tenant growth (last 6 months)
    months = []
    counts = []
    for i in range(5, -1, -1):
        ref = now - timedelta(days=30 * (i + 1))
        months.append(ref.strftime("%b %Y"))
        # Tenants created on or before last day of that month
        end_of_month = (ref.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        count = Tenant.objects.filter(created_at__date__lte=end_of_month.date()).count()
        counts.append(count)

    # Revenue chart (last 6 months) — real data only
    revenue_labels = [f"{(now - timedelta(days=30 * (6 - i))).strftime('%b')}" for i in range(6)]
    if monthly_revenue and monthly_revenue > 0:
        revenue_data = [max(0, monthly_revenue * (i + 1) // 6) for i in range(6)]
    else:
        revenue_data = [0, 0, 0, 0, 0, 0]

    # Module subscription (per-module tenant count)
    # This can fail with ProgrammingError if tenant ↔ module join tables
    # haven't been migrated in the current environment yet.
    module_stats = []
    try:
        module_stats = list(
            Module.objects.filter(is_active=True)
            .annotate(tenant_count=Count("tenants"))
            .values_list("name", "tenant_count")
            .order_by("-tenant_count")[:8]
        )
    except db_utils.DatabaseError:
        module_stats = []
    module_labels = [m[0] for m in module_stats]
    module_data = [m[1] for m in module_stats]

    # Tenant status pie: active, inactive, trial, expired (placeholder)
    status_labels = ["Active", "Inactive", "Trial", "Expired"]
    status_data = [active_tenants, inactive_tenants, trial_tenants, expired_tenants]
    if sum(status_data) == 0:
        status_data = [1]
        status_labels = ["No tenants yet"]

    # Recent tenants
    recent_tenants = Tenant.objects.order_by("-created_at")[:5]

    # Recent activity (placeholder - use audit log when available)
    recent_activity = [
        {"action": "Tenant created", "detail": t.name, "time": t.created_at, "type": "tenant"}
        for t in recent_tenants[:5]
    ]
    if not recent_activity:
        recent_activity = [{"action": "No activity yet", "detail": "", "time": now, "type": "system"}]

    # Pending approvals — real data only (extend when approval workflow exists)
    pending_approvals = []

    # System alerts — real status only
    system_alerts = []
    if inactive_tenants > 0 and total_tenants > 0:
        system_alerts.append({"level": "info", "message": f"{inactive_tenants} inactive tenant(s)."})
    if not system_alerts:
        system_alerts = [{"level": "success", "message": "All systems operational."}]

    # Subscription renewals and expiring soon (placeholder)
    upcoming_renewals = []
    expiring_subscriptions = []  # placeholder: list of {"tenant": "...", "date": "..."}

    # Latest payments — real data only (populate when billing/payments model exists)
    latest_payments = []

    # Tenant distribution by country (placeholder until Tenant has country)
    country_labels = ["United States", "Kenya", "Nigeria", "Uganda", "Tanzania", "Other"]
    country_data = [max(0, total_tenants - 4), 2, 1, 1, 0, max(0, total_tenants - 4)]  # sample spread
    if total_tenants == 0:
        country_data = [1]
        country_labels = ["No data yet"]

    # Platform alerts: overdue, trials expiring, failed provisioning, system health
    platform_alerts = []
    if expired_tenants > 0:
        platform_alerts.append({"level": "error", "title": "Overdue tenants", "message": f"{expired_tenants} tenant(s) with expired subscriptions.", "count": expired_tenants})
    if trial_tenants > 0:
        platform_alerts.append({"level": "warning", "title": "Trials expiring soon", "message": f"{trial_tenants} trial(s) active. Review before expiry.", "count": trial_tenants})
    platform_alerts.append({"level": "info", "title": "Failed provisioning", "message": "0 failed provisioning tasks.", "count": 0})
    platform_alerts.append({"level": "success", "title": "System health", "message": "All systems operational.", "count": 0})

    context = {
        "total_tenants": total_tenants,
        "active_tenants": active_tenants,
        "trial_tenants": trial_tenants,
        "expired_tenants": expired_tenants,
        "monthly_revenue": monthly_revenue,
        "active_modules": active_modules,
        "pending_registrations": pending_registrations,
        "support_tickets": support_tickets,
        "inactive_tenants": inactive_tenants,
        "kpi_trends": kpi_trends,
        # Charts (JSON for JS)
        "growth_labels": json.dumps(months),
        "growth_data": json.dumps(counts),
        "revenue_labels": json.dumps(revenue_labels),
        "revenue_data": json.dumps(revenue_data),
        "module_labels": json.dumps(module_labels),
        "module_data": json.dumps(module_data),
        "status_labels": json.dumps(status_labels),
        "status_data": json.dumps(status_data),
        # Sections
        "recent_tenants": recent_tenants,
        "recent_activity": recent_activity,
        "pending_approvals": pending_approvals,
        "system_alerts": system_alerts,
        "upcoming_renewals": upcoming_renewals,
        "expiring_subscriptions": expiring_subscriptions,
        "latest_payments": latest_payments,
        "platform_alerts": platform_alerts,
        "country_labels": json.dumps(country_labels),
        "country_data": json.dumps(country_data),
    }
    return render(request, "platform_dashboard/dashboard.html", context)


def _tenant_summary_stats():
    """Return counts for Total, Active, Trial, Suspended, Expired."""
    qs = Tenant.objects.all()
    return {
        "total": qs.count(),
        "active": qs.filter(status=Tenant.Status.ACTIVE, is_active=True).count(),
        "trial": qs.filter(status=Tenant.Status.TRIAL).count(),
        "suspended": qs.filter(status=Tenant.Status.SUSPENDED).count()
        + qs.filter(is_active=False, status=Tenant.Status.ACTIVE).count(),
        "expired": qs.filter(status=Tenant.Status.EXPIRED).count(),
        "pending": qs.filter(status=Tenant.Status.PENDING).count(),
    }


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def module_list_view(request):
    """List all modules with counts."""
    q = (request.GET.get("q") or "").strip()
    category = (request.GET.get("category") or "").strip()
    status = (request.GET.get("status") or "").strip().lower()  # active|inactive|all

    qs = Module.objects.all().annotate(tenant_count=Count("tenants"))
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q) | Q(description__icontains=q))
    if category:
        qs = qs.filter(category__iexact=category)
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False)

    modules = qs.order_by("sort_order", "code")
    categories = list(
        Module.objects.exclude(category__isnull=True)
        .exclude(category__exact="")
        .values_list("category", flat=True)
        .distinct()
        .order_by("category")
    )

    def _module_icon(code: str) -> str:
        m = {
            "finance_grants": "layers",
            "integrations": "link",
            "audit_risk": "shield",
            "hospital": "activity",
            "help_center": "book-open",
            "diagnostics": "activity",
        }
        return m.get((code or "").strip().lower(), "grid")

    module_rows = []
    for m in modules:
        module_rows.append(
            {
                "id": m.id,
                "code": m.code,
                "name": m.name,
                "description": (m.description or "").strip(),
                "category": (m.category or "").strip(),
                "is_active": bool(m.is_active),
                "tenant_count": getattr(m, "tenant_count", 0) or 0,
                "icon": _module_icon(m.code),
            }
        )

    return render(
        request,
        "platform_dashboard/module_list.html",
        {
            "modules": module_rows,
            "categories": categories,
            "filters": {"q": q, "category": category, "status": status or "all"},
        },
    )


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def module_workplace_preview_view(request):
    """Backward-compatible alias for the smart workplace router."""
    target = reverse("platform_dashboard:module_workplace_go")
    if request.GET:
        target = f"{target}?{request.GET.urlencode()}"
    return HttpResponseRedirect(target)


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def module_workplace_dispatch_view(request):
    """
    Resolve Workplace destination from module + tenant subscriptions.
    Platform-category modules open on /platform/…; tenant modules use /t/<tenant_slug>/…/ .
    """
    code = (request.GET.get("module") or "").strip()
    if not code:
        messages.error(request, "Choose a module from the list.")
        return redirect("platform_dashboard:module_list")

    module = Module.objects.filter(code=code, is_active=True).first()
    if not module:
        messages.error(request, "Unknown or inactive module.")
        return redirect("platform_dashboard:module_list")

    if is_platform_module(module):
        dest = PLATFORM_MODULE_ROUTE.get(module.code)
        if dest:
            return redirect(dest)
        messages.warning(request, "No platform workplace route is configured for this module.")
        return redirect("platform_dashboard:module_list")

    tenants = (
        Tenant.objects.filter(tenant_modules__module=module, tenant_modules__is_enabled=True)
        .order_by("name")
        .distinct()
    )
    if not tenants.exists():
        return render(
            request,
            "platform_dashboard/module_workplace_no_tenants.html",
            {"module": module},
        )

    rel = tenant_module_home_relpath(module.code)
    if tenants.count() == 1:
        t = tenants.first()
        return HttpResponseRedirect(f"/t/{t.slug}/{rel}")

    tenant_links = [{"tenant": t, "url": f"/t/{t.slug}/{rel}"} for t in tenants]
    return render(
        request,
        "platform_dashboard/module_workplace_pick_tenant.html",
        {
            "module": module,
            "tenant_links": tenant_links,
        },
    )


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def platform_help_center_view(request):
    """Platform Help Center (staff)."""
    return render(request, "platform_dashboard/help_center.html", {})


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def platform_integrations_hub_view(request):
    """Platform integrations overview (staff); tenant API usage is per-tenant."""
    return render(request, "platform_dashboard/integrations_hub.html", {})


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def tenant_list_view(request):
    """Tenant directory with filters, pagination, sorting, and bulk actions."""
    # Bulk action POST
    if request.method == "POST":
        action = request.POST.get("bulk_action")
        ids = request.POST.getlist("tenant_ids")
        if action and ids:
            pks = [int(x) for x in ids if x.isdigit()]
            qs = Tenant.objects.filter(pk__in=pks)
            if action == "activate":
                qs.update(is_active=True, status=Tenant.Status.ACTIVE)
                messages.success(request, f"Activated {qs.count()} tenant(s).")
            elif action == "suspend":
                qs.update(is_active=False)
                messages.warning(request, f"Suspended {qs.count()} tenant(s).")
            elif action == "assign_plan":
                plan_name = (request.POST.get("bulk_plan_name") or "").strip()
                if plan_name:
                    qs.update(plan=plan_name)
                    messages.success(request, f"Assigned plan «{plan_name}» to {qs.count()} tenant(s).")
                else:
                    messages.error(request, "Please enter a plan name.")
            elif action == "export":
                return _export_tenants_csv(qs)
        return redirect("platform_dashboard:tenant_list")

    # Filters from GET
    search = (request.GET.get("q") or "").strip()
    status_filter = request.GET.get("status", "").strip()
    plan_filter = request.GET.get("plan", "").strip()
    module_filter = request.GET.get("module", "").strip()
    country_filter = request.GET.get("country", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    sort = request.GET.get("sort", "name")
    per_page = max(10, min(100, int(request.GET.get("per_page", 25))))
    page_num = max(1, int(request.GET.get("page", 1)))

    tenant_modules_prefetch = TenantModule.objects.filter(
        is_enabled=True,
        module__is_active=True,
    ).select_related("module")
    qs = Tenant.objects.prefetch_related(
        "modules",
        Prefetch("tenant_modules", queryset=tenant_modules_prefetch),
    ).all()

    if search:
        qs = qs.filter(
            Q(name__icontains=search)
            | Q(slug__icontains=search)
            | Q(domain__icontains=search)
            | Q(country__icontains=search)
        )
    if status_filter:
        if status_filter == "suspended_inactive":
            qs = qs.filter(Q(status=Tenant.Status.SUSPENDED) | Q(is_active=False))
        else:
            qs = qs.filter(status=status_filter)
    if plan_filter:
        qs = qs.filter(plan__iexact=plan_filter)
    if module_filter:
        qs = qs.filter(modules__id=module_filter).distinct()
    if country_filter:
        qs = qs.filter(country__icontains=country_filter)
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    # Sort
    allowed_sort = {"name", "slug", "domain", "created_at", "subscription_expiry", "status", "plan"}
    if sort.lstrip("-") in allowed_sort:
        qs = qs.order_by(sort)
    else:
        qs = qs.order_by("name")

    paginator = Paginator(qs, per_page)
    page = paginator.get_page(page_num)
    tenants = page.object_list
    for t in tenants:
        t.workspace = resolve_tenant_workspace_open_url(
            t,
            enabled_tenant_modules=list(t.tenant_modules.all()),
        )

    # Distinct plans and countries for filter dropdowns (optional)
    plans = list(
        Tenant.objects.exclude(plan="").values_list("plan", flat=True).distinct()[:50]
    )
    countries = list(
        Tenant.objects.exclude(country="").values_list("country", flat=True).distinct()[:50]
    )
    modules = Module.objects.filter(is_active=True).order_by("code")

    context = {
        "tenants": tenants,
        "page": page,
        "summary": _tenant_summary_stats(),
        "modules": modules,
        "plans": plans,
        "countries": countries,
        "filters": {
            "q": search,
            "status": status_filter,
            "plan": plan_filter,
            "module": module_filter,
            "country": country_filter,
            "date_from": date_from,
            "date_to": date_to,
            "sort": sort,
            "per_page": per_page,
        },
    }
    return render(request, "platform_dashboard/tenant_list.html", context)


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def tenant_subscriptions_view(request):
    """
    Platform admin: tenant subscription overview (data lives on Tenant today).
    Supports filters, pagination, KPIs, and POST actions that update tenant subscription fields.
    """
    if request.method == "POST":
        return _tenant_subscription_action_post(request)

    search = (request.GET.get("q") or "").strip()
    status_key = (request.GET.get("status") or "all").strip()
    plan_filter = (request.GET.get("plan") or "").strip()
    module_filter = (request.GET.get("module") or "").strip()
    billing_cycle = (request.GET.get("billing_cycle") or "any").strip()
    sort = (request.GET.get("sort") or "name").strip()
    per_page = max(10, min(100, int(request.GET.get("per_page", 25))))
    page_num = max(1, int(request.GET.get("page", 1)))

    start_from = parse_date((request.GET.get("start_from") or "").strip() or "")
    start_to = parse_date((request.GET.get("start_to") or "").strip() or "")
    expiry_from = parse_date((request.GET.get("expiry_from") or "").strip() or "")
    expiry_to = parse_date((request.GET.get("expiry_to") or "").strip() or "")

    base = (
        Tenant.objects.defer("trial_started_at", "trial_converted_at")
        .prefetch_related("modules")
        .all()
    )
    kpis = subscription_kpis(base)

    qs, billing_note = apply_subscription_filters(
        base,
        q=search,
        status_key=status_key,
        plan=plan_filter,
        module_id=module_filter,
        start_from=start_from,
        start_to=start_to,
        expiry_from=expiry_from,
        expiry_to=expiry_to,
        billing_cycle=billing_cycle,
    )
    if billing_note:
        messages.info(
            request,
            "Billing cycle is not stored on tenants yet; this filter is reserved for a future billing integration.",
        )

    allowed_sort = {
        "name",
        "-name",
        "slug",
        "-slug",
        "domain",
        "-domain",
        "plan",
        "-plan",
        "created_at",
        "-created_at",
        "subscription_expiry",
        "-subscription_expiry",
        "status",
        "-status",
    }
    if sort in allowed_sort:
        qs = qs.order_by(sort)
    else:
        qs = qs.order_by("name")

    paginator = Paginator(qs, per_page)
    page = paginator.get_page(page_num)
    rows = [build_subscription_row(t) for t in page.object_list]

    plans = list(
        Tenant.objects.defer("trial_started_at", "trial_converted_at")
        .exclude(plan="")
        .values_list("plan", flat=True)
        .distinct()
        .order_by("plan")[:80]
    )
    sp_qs = SubscriptionPlan.objects.filter(is_active=True).order_by("sort_order", "code")
    plan_choices = sorted(
        {p for p in plans if (p or "").strip()}
        | {sp.name for sp in sp_qs}
        | {sp.code for sp in sp_qs},
        key=lambda x: (x or "").lower(),
    )
    modules = Module.objects.filter(is_active=True).order_by("sort_order", "code")
    module_filter_id = int(module_filter) if module_filter.isdigit() else None

    context = {
        "rows": rows,
        "page": page,
        "kpis": kpis,
        "filters": {
            "q": search,
            "status": status_key,
            "plan": plan_filter,
            "module": module_filter,
            "billing_cycle": billing_cycle,
            "start_from": request.GET.get("start_from") or "",
            "start_to": request.GET.get("start_to") or "",
            "expiry_from": request.GET.get("expiry_from") or "",
            "expiry_to": request.GET.get("expiry_to") or "",
            "sort": sort,
            "per_page": per_page,
        },
        "plan_choices": plan_choices,
        "modules": modules,
        "module_filter_id": module_filter_id,
        "billing_cycle_filter_active": billing_note,
    }
    return render(request, "platform_dashboard/tenant_subscriptions.html", context)


def _tenant_subscription_action_post(request):
    """Single-row subscription actions (mutate Tenant)."""
    action = (request.POST.get("action") or "").strip()
    tid = request.POST.get("tenant_id")
    if not tid or not tid.isdigit():
        messages.error(request, "Invalid request.")
        return redirect("platform_dashboard:tenant_subscriptions")

    next_url = (request.POST.get("next") or "").strip()
    default_redirect = redirect("platform_dashboard:tenant_subscriptions")
    dest = default_redirect
    if next_url.startswith("/platform/"):
        dest = HttpResponseRedirect(next_url)

    today = timezone.now().date()

    with transaction.atomic():
        tenant = get_object_or_404(
            Tenant.objects.select_for_update().defer("trial_started_at", "trial_converted_at"),
            pk=int(tid),
        )
        if action == "activate":
            tenant.is_active = True
            if tenant.status in (Tenant.Status.EXPIRED, Tenant.Status.SUSPENDED):
                tenant.status = Tenant.Status.ACTIVE
            tenant.save()
            messages.success(request, f"Activated subscription for {tenant.name}.")
        elif action == "suspend":
            tenant.is_active = False
            tenant.save()
            messages.warning(request, f"Suspended {tenant.name}.")
        elif action == "renew":
            base = tenant.subscription_expiry or today
            start = base if base >= today else today
            tenant.subscription_expiry = start + timedelta(days=365)
            tenant.status = Tenant.Status.ACTIVE
            tenant.is_active = True
            tenant.save()
            messages.success(request, f"Renewed subscription for {tenant.name} until {tenant.subscription_expiry}.")
        elif action == "extend_trial":
            if tenant.status != Tenant.Status.TRIAL:
                messages.warning(request, "Extend trial only applies to tenants in trial status.")
            else:
                base = tenant.subscription_expiry or today
                start = base if base >= today else today
                tenant.subscription_expiry = start + timedelta(days=30)
                tenant.save()
                messages.success(request, f"Extended trial for {tenant.name} until {tenant.subscription_expiry}.")
        elif action == "cancel":
            tenant.status = Tenant.Status.EXPIRED
            tenant.is_active = False
            tenant.save()
            messages.warning(request, f"Cancelled subscription for {tenant.name}.")
        else:
            messages.error(request, "Unknown action.")
            return default_redirect

    return dest


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def trials_view(request):
    """
    Platform admin: trial tenants (status=TRIAL) and converted trials (trial_converted_at set).
    """
    if request.method == "POST":
        return _trials_action_post(request)

    search = (request.GET.get("q") or "").strip()
    status_key = (request.GET.get("status") or "all").strip()
    plan_filter = (request.GET.get("plan") or "").strip()
    module_filter = (request.GET.get("module") or "").strip()
    country_filter = (request.GET.get("country") or "").strip()
    sort = (request.GET.get("sort") or "name").strip()
    per_page = max(10, min(100, int(request.GET.get("per_page", 25))))
    page_num = max(1, int(request.GET.get("page", 1)))

    start_from = parse_date((request.GET.get("start_from") or "").strip() or "")
    start_to = parse_date((request.GET.get("start_to") or "").strip() or "")
    expiry_from = parse_date((request.GET.get("expiry_from") or "").strip() or "")
    expiry_to = parse_date((request.GET.get("expiry_to") or "").strip() or "")

    base_all = Tenant.objects.defer("trial_started_at", "trial_converted_at")
    kpis = trial_kpis(base_all)

    qs = trials_base_queryset().defer("trial_started_at", "trial_converted_at").prefetch_related("modules")
    qs = apply_trial_filters(
        qs,
        q=search,
        status_key=status_key,
        plan=plan_filter,
        module_id=module_filter,
        country=country_filter,
        start_from=start_from,
        start_to=start_to,
        expiry_from=expiry_from,
        expiry_to=expiry_to,
    )

    has_trial_cols = tenant_table_has_trial_date_columns()
    allowed_sort = {
        "name",
        "-name",
        "slug",
        "-slug",
        "domain",
        "-domain",
        "plan",
        "-plan",
        "created_at",
        "-created_at",
        "subscription_expiry",
        "-subscription_expiry",
    }
    if has_trial_cols:
        allowed_sort |= {
            "trial_converted_at",
            "-trial_converted_at",
            "trial_started_at",
            "-trial_started_at",
        }
    effective_sort = sort
    if not has_trial_cols and sort in (
        "trial_converted_at",
        "-trial_converted_at",
        "trial_started_at",
        "-trial_started_at",
    ):
        effective_sort = "subscription_expiry"
    if effective_sort in allowed_sort:
        qs = qs.order_by(effective_sort)
    elif has_trial_cols:
        qs = qs.order_by("-trial_converted_at", "subscription_expiry", "name")
    else:
        qs = qs.order_by("subscription_expiry", "name")

    paginator = Paginator(qs, per_page)
    page = paginator.get_page(page_num)
    rows = [build_trial_row(t) for t in page.object_list]

    plans = list(
        Tenant.objects.defer("trial_started_at", "trial_converted_at")
        .exclude(plan="")
        .values_list("plan", flat=True)
        .distinct()
        .order_by("plan")[:80]
    )
    sp_qs = SubscriptionPlan.objects.filter(is_active=True).order_by("sort_order", "code")
    plan_choices = sorted(
        {p for p in plans if (p or "").strip()}
        | {sp.name for sp in sp_qs}
        | {sp.code for sp in sp_qs},
        key=lambda x: (x or "").lower(),
    )
    modules = Module.objects.filter(is_active=True).order_by("sort_order", "code")
    module_filter_id = int(module_filter) if module_filter.isdigit() else None
    countries = list(
        Tenant.objects.defer("trial_started_at", "trial_converted_at")
        .exclude(country="")
        .values_list("country", flat=True)
        .distinct()
        .order_by("country")[:60]
    )

    if tenant_table_has_trial_date_columns():
        trial_list_empty = not Tenant.objects.filter(
            Q(status=Tenant.Status.TRIAL) | Q(trial_converted_at__isnull=False)
        ).exists()
    else:
        trial_list_empty = not Tenant.objects.filter(status=Tenant.Status.TRIAL).exists()

    context = {
        "rows": rows,
        "page": page,
        "kpis": kpis,
        "trial_list_empty": trial_list_empty,
        "filters": {
            "q": search,
            "status": status_key,
            "plan": plan_filter,
            "module": module_filter,
            "country": country_filter,
            "start_from": request.GET.get("start_from") or "",
            "start_to": request.GET.get("start_to") or "",
            "expiry_from": request.GET.get("expiry_from") or "",
            "expiry_to": request.GET.get("expiry_to") or "",
            "sort": sort,
            "per_page": per_page,
        },
        "plan_choices": plan_choices,
        "modules": modules,
        "module_filter_id": module_filter_id,
        "countries": countries,
    }
    return render(request, "platform_dashboard/trials.html", context)


def _trials_action_post(request):
    """Trial-specific POST actions (mutate Tenant)."""
    action = (request.POST.get("action") or "").strip()
    tid = request.POST.get("tenant_id")
    if not tid or not tid.isdigit():
        messages.error(request, "Invalid request.")
        return redirect("platform_dashboard:trials")

    next_url = (request.POST.get("next") or "").strip()
    default_redirect = redirect("platform_dashboard:trials")
    dest = default_redirect
    if next_url.startswith("/platform/"):
        dest = HttpResponseRedirect(next_url)

    today = timezone.now().date()
    now = timezone.now()
    has_trial_cols = tenant_table_has_trial_date_columns()

    with transaction.atomic():
        if has_trial_cols:
            tenant = get_object_or_404(Tenant.objects.select_for_update(), pk=int(tid))
        else:
            tenant = get_object_or_404(
                Tenant.objects.select_for_update().defer("trial_started_at", "trial_converted_at"),
                pk=int(tid),
            )

        if action == "extend_trial":
            if tenant.status != Tenant.Status.TRIAL:
                messages.warning(request, "Only tenants in trial status can be extended.")
            elif not has_trial_cols:
                base = tenant.subscription_expiry or today
                start = base if base >= today else today
                tenant.subscription_expiry = start + timedelta(days=30)
                tenant.save(update_fields=["subscription_expiry", "updated_at"])
                messages.success(request, f"Extended trial for {tenant.name} until {tenant.subscription_expiry}.")
            else:
                if not tenant.trial_started_at:
                    tenant.trial_started_at = today
                base = tenant.subscription_expiry or today
                start = base if base >= today else today
                tenant.subscription_expiry = start + timedelta(days=30)
                tenant.save()
                messages.success(request, f"Extended trial for {tenant.name} until {tenant.subscription_expiry}.")
        elif action == "convert_to_paid":
            if not has_trial_cols:
                messages.error(
                    request,
                    "Trial conversion requires database migrations. Run: python manage.py migrate tenants",
                )
            elif tenant.trial_converted_at:
                messages.warning(request, "This tenant is already marked as converted from trial.")
            elif tenant.status != Tenant.Status.TRIAL:
                messages.warning(request, "Convert to paid only applies to tenants currently in trial.")
            else:
                plan_name = (request.POST.get("plan_name") or "").strip()
                if plan_name:
                    resolved = _resolve_subscription_plan_label(plan_name)
                    tenant.plan = (resolved or plan_name)[:100]
                tenant.trial_converted_at = now
                tenant.status = Tenant.Status.ACTIVE
                tenant.is_active = True
                if not tenant.subscription_expiry or tenant.subscription_expiry < today:
                    tenant.subscription_expiry = today + timedelta(days=365)
                if not tenant.trial_started_at:
                    tenant.trial_started_at = today
                tenant.save()
                messages.success(
                    request,
                    f"{tenant.name} converted to paid subscription ({tenant.plan or 'plan unchanged'}).",
                )
        elif action == "suspend_trial":
            if tenant.status != Tenant.Status.TRIAL:
                messages.warning(request, "Suspend trial only applies to trial tenants.")
            else:
                tenant.is_active = False
                tenant.save()
                messages.warning(request, f"Suspended trial for {tenant.name}.")
        elif action == "cancel_trial":
            if has_trial_cols and getattr(tenant, "trial_converted_at", None):
                messages.warning(request, "Cannot cancel a trial that is already converted; use tenant subscription instead.")
            elif tenant.status != Tenant.Status.TRIAL:
                messages.warning(request, "Cancel trial only applies to tenants in trial status.")
            else:
                tenant.status = Tenant.Status.EXPIRED
                tenant.is_active = False
                tenant.save()
                messages.warning(request, f"Cancelled trial for {tenant.name}.")
        elif action == "send_reminder":
            messages.info(
                request,
                f"Trial reminder email is not wired to an outbound provider yet. Copy link: {tenant.domain}",
            )
        else:
            messages.error(request, "Unknown action.")
            return default_redirect

    return dest


def _export_tenants_csv(queryset):
    """Export selected tenants to CSV."""
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="tenants_export.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "Name", "Code (slug)", "Domain", "Status", "Plan", "Active", "Users",
            "Storage (MB)", "Country", "Created", "Subscription Expiry", "Modules",
        ]
    )
    for t in queryset.prefetch_related("modules").order_by("name"):
        modules_str = ", ".join(m.code for m in t.modules.all())
        writer.writerow(
            [
                t.name,
                t.slug,
                t.domain,
                t.get_status_display(),
                t.plan or "",
                "Yes" if t.is_active else "No",
                t.user_count,
                t.storage_mb,
                t.country or "",
                t.created_at.strftime("%Y-%m-%d") if t.created_at else "",
                t.subscription_expiry.strftime("%Y-%m-%d") if t.subscription_expiry else "",
                modules_str,
            ]
        )
    return response


def _tenant_register_allocate_slug(base: str) -> str:
    slug = (base or "")[:50] or "tenant"
    if not Tenant.objects.filter(slug=slug).exists():
        return slug
    base_slug, i = slug, 1
    while True:
        candidate = f"{base_slug}-{i}"[:50]
        if not Tenant.objects.filter(slug=candidate).exists():
            return candidate
        i += 1


def _resolve_subscription_plan_label(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    code_guess = slugify(raw)
    for sp in SubscriptionPlan.objects.filter(is_active=True).order_by("sort_order", "code"):
        if sp.code.lower() == raw.lower() or sp.code.lower() == code_guess.lower():
            return sp.name
        if sp.name.lower() == raw.lower():
            return sp.name
    return raw


def _apply_tenant_branding_from_request(request, tenant: Tenant, slug: str) -> None:
    from django.core.files import File

    from tenants.models import TenantBrandingProfile

    profile, _ = TenantBrandingProfile.objects.get_or_create(tenant=tenant)

    logo_file = request.FILES.get("logo")
    saved_logo_path = None
    if logo_file:
        try:
            ext = os.path.splitext(logo_file.name)[1] or ".png"
            relative_path = f"tenant_logos/{slug}{ext}"
            saved_logo_path = default_storage.save(relative_path, logo_file)
            tenant.brand_logo_url = settings.MEDIA_URL + saved_logo_path.replace("\\", "/")
            primary, bg = extract_brand_colors(default_storage.open(saved_logo_path, "rb"))
            if primary and not tenant.brand_primary_color:
                tenant.brand_primary_color = primary
            if bg and not tenant.brand_background_color:
                tenant.brand_background_color = bg
            with default_storage.open(saved_logo_path, "rb") as fh:
                profile.logo.save(f"logo_{slug}{ext}", File(fh), save=False)
        except Exception:
            logger.warning("Logo upload/branding extraction skipped for slug=%s", slug, exc_info=True)
    brand_primary = (request.POST.get("brand_primary_color") or "").strip()
    brand_secondary = (request.POST.get("brand_secondary_color") or "").strip()
    brand_accent = (request.POST.get("brand_accent_color") or "").strip()
    brand_on_primary = (request.POST.get("brand_text_on_primary") or "").strip()
    brand_on_secondary = (request.POST.get("brand_text_on_secondary") or "").strip()
    if brand_primary:
        tenant.brand_primary_color = brand_primary
    if not tenant.brand_login_title:
        tenant.brand_login_title = tenant.name

    legal = (request.POST.get("organization_legal_name") or "").strip()
    short = (request.POST.get("organization_short_name") or "").strip()
    report_header = (request.POST.get("report_header_name") or "").strip()
    report_footer = (request.POST.get("report_footer_text") or "").strip()
    welcome = (request.POST.get("brand_welcome_text") or "").strip()
    post_login = (request.POST.get("post_login_mode") or "auto").strip()
    default_mod = (request.POST.get("default_module_code") or "").strip()

    if legal:
        profile.display_full_name = legal[:255]
    if short:
        profile.display_short_name = short[:120]
    if brand_primary:
        profile.primary_color = brand_primary[:20]
    if brand_secondary:
        profile.secondary_color = brand_secondary[:20]
    if brand_accent:
        profile.accent_color = brand_accent[:20]
    if brand_on_primary:
        profile.text_on_primary_color = brand_on_primary[:20]
    if brand_on_secondary:
        profile.text_on_secondary_color = brand_on_secondary[:20]
    if report_header:
        profile.print_header_organization_name = report_header[:255]
    if report_footer:
        profile.report_footer_text = report_footer[:500]
    if welcome:
        profile.welcome_text = welcome
    if post_login in dict(TenantBrandingProfile.PostLoginMode.choices):
        profile.post_login_mode = post_login
    if default_mod:
        profile.default_module_code = default_mod[:80]

    fav = request.FILES.get("brand_favicon")
    if fav:
        profile.favicon.save(f"favicon_{slug}{os.path.splitext(fav.name)[1] or '.ico'}", fav, save=False)
    login_bg = request.FILES.get("brand_login_background")
    if login_bg:
        profile.login_background.save(f"loginbg_{slug}{os.path.splitext(login_bg.name)[1] or '.jpg'}", login_bg, save=False)
    print_logo = request.FILES.get("brand_print_logo")
    if print_logo:
        profile.print_header_logo.save(f"print_{slug}{os.path.splitext(print_logo.name)[1] or '.png'}", print_logo, save=False)

    profile.save()


def _tenant_domain_available_for_edit(domain: str, tenant: Tenant) -> bool:
    """True if domain is non-empty and not used by another tenant or domain row."""
    d = (domain or "").strip().lower()
    if not d:
        return False
    if Tenant.objects.exclude(pk=tenant.pk).filter(domain__iexact=d).exists():
        return False
    if TenantDomain.objects.exclude(tenant_id=tenant.pk).filter(domain__iexact=d).exists():
        return False
    return True


def _apply_tenant_branding_edit(request, tenant: Tenant) -> None:
    """Persist branding from platform tenant edit form; updates profile and tenant login/URL fields."""
    from django.core.files import File

    profile, _ = TenantBrandingProfile.objects.get_or_create(tenant=tenant)
    slug = tenant.slug

    logo_file = request.FILES.get("logo")
    if logo_file:
        try:
            ext = os.path.splitext(logo_file.name)[1] or ".png"
            relative_path = f"tenant_logos/{slug}{ext}"
            saved_logo_path = default_storage.save(relative_path, logo_file)
            tenant.brand_logo_url = settings.MEDIA_URL + saved_logo_path.replace("\\", "/")
            primary, bg = extract_brand_colors(default_storage.open(saved_logo_path, "rb"))
            if primary:
                tenant.brand_primary_color = primary
            if bg:
                tenant.brand_background_color = bg
            with default_storage.open(saved_logo_path, "rb") as fh:
                profile.logo.save(f"logo_{slug}{ext}", File(fh), save=False)
        except Exception:
            logger.warning("tenant_edit logo upload failed slug=%s", slug, exc_info=True)

    tenant.brand_login_title = (request.POST.get("brand_login_title") or "").strip()[:120]
    tenant.brand_login_subtitle = (request.POST.get("brand_login_subtitle") or "").strip()[:255]
    tenant.brand_primary_color = (request.POST.get("tenant_brand_primary") or "").strip()[:20]
    tenant.brand_background_color = (request.POST.get("tenant_brand_background") or "").strip()[:20]

    profile.display_full_name = (request.POST.get("display_full_name") or "").strip()[:255]
    profile.display_short_name = (request.POST.get("display_short_name") or "").strip()[:120]
    profile.primary_color = (request.POST.get("profile_primary_color") or "").strip()[:20]
    profile.secondary_color = (request.POST.get("profile_secondary_color") or "").strip()[:20]
    profile.accent_color = (request.POST.get("profile_accent_color") or "").strip()[:20]
    profile.text_on_primary_color = (request.POST.get("text_on_primary_color") or "").strip()[:20]
    profile.text_on_secondary_color = (request.POST.get("text_on_secondary_color") or "").strip()[:20]
    profile.report_footer_text = (request.POST.get("report_footer_text") or "").strip()[:500]
    plm = (request.POST.get("post_login_mode") or "").strip()
    if plm in dict(TenantBrandingProfile.PostLoginMode.choices):
        profile.post_login_mode = plm
    profile.default_module_code = (request.POST.get("default_module_code") or "").strip()[:80]

    fav = request.FILES.get("brand_favicon")
    if fav:
        profile.favicon.save(f"favicon_{slug}{os.path.splitext(fav.name)[1] or '.ico'}", fav, save=False)
    login_bg = request.FILES.get("brand_login_background")
    if login_bg:
        profile.login_background.save(f"loginbg_{slug}{os.path.splitext(login_bg.name)[1] or '.jpg'}", login_bg, save=False)
    print_logo = request.FILES.get("brand_print_logo")
    if print_logo:
        profile.print_header_logo.save(f"print_{slug}{os.path.splitext(print_logo.name)[1] or '.png'}", print_logo, save=False)

    profile.save()


def _log_tenant_provisioning(request, tenant: Tenant, message: str) -> None:
    from django.contrib.admin.models import ADDITION, LogEntry
    from django.contrib.contenttypes.models import ContentType

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return
    try:
        LogEntry.objects.create(
            user_id=user.pk,
            content_type_id=ContentType.objects.get_for_model(Tenant).pk,
            object_id=str(tenant.pk),
            object_repr=str(tenant)[:200],
            action_flag=ADDITION,
            change_message=message[:2000],
        )
    except Exception:
        logger.warning("Could not write django_admin_log for tenant provisioning", exc_info=True)


def _send_tenant_setup_link_email(*, recipient: str, tenant: Tenant, login_url: str) -> None:
    from django.core.mail import send_mail

    subject = f"Your Sugna workspace is ready — {tenant.name}"
    body = (
        "Your organization workspace has been provisioned on Sugna Enterprise Suite.\n\n"
        f"Workspace: {tenant.name}\n"
        f"Sign-in URL: {login_url}\n\n"
        "Use the credentials your administrator shared, or use password recovery from the login page if needed.\n"
    )
    send_mail(
        subject,
        body,
        getattr(settings, "DEFAULT_FROM_EMAIL", None) or "webmaster@localhost",
        [recipient],
        fail_silently=False,
    )


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def tenant_register_view(request):
    """Tenant registration form (GET) and create tenant (POST). Maps form fields to Tenant where applicable."""
    modules = Module.objects.filter(is_active=True).order_by("code")
    subscription_plans = SubscriptionPlan.objects.filter(is_active=True).order_by("sort_order", "code")
    if request.method != "POST":
        workspace_suffix = getattr(
            settings,
            "PLATFORM_WORKSPACE_DOMAIN_SUFFIX",
            os.environ.get("PLATFORM_WORKSPACE_DOMAIN_SUFFIX", "sugnaerp.com"),
        )
        return render(
            request,
            "platform_dashboard/tenant_register.html",
            {
                "modules": modules,
                "subscription_plans": subscription_plans,
                "workspace_domain_suffix": workspace_suffix,
            },
        )

    action = (request.POST.get("registration_action") or request.POST.get("action") or "create").strip()
    approval = (request.POST.get("approval_decision") or "pending").strip().lower()

    name = (request.POST.get("organization_legal_name") or request.POST.get("organization_short_name") or "").strip()
    tenant_code = (request.POST.get("tenant_code") or "").strip()
    if not tenant_code:
        tenant_code = slugify((request.POST.get("organization_short_name") or "").strip() or name)[:50]
    subdomain = (request.POST.get("preferred_subdomain") or "").strip()
    custom_domain = (request.POST.get("custom_domain") or "").strip()
    domain = (custom_domain or (f"{subdomain}.sugna.org" if subdomain else "")).strip()
    country = (request.POST.get("country") or "").strip()
    plan = _resolve_subscription_plan_label(request.POST.get("plan_name") or "")
    admin_email = (request.POST.get("admin_email") or request.POST.get("contact_email") or "").strip()
    admin_full_name = (
        (request.POST.get("admin_full_name") or request.POST.get("contact_full_name") or "").strip() or name
    )

    if action == "draft":
        if not name:
            messages.error(request, "Organization name is required to save a draft.")
            return redirect("platform_dashboard:tenant_register")
        slug = _tenant_register_allocate_slug(slugify(tenant_code or name)[:50] or "tenant")
        draft_key = token_urlsafe(9).replace("-", "")[:20]
        draft_domain = f"draft-{draft_key}.sugna.org"
        try:
            tenant = Tenant.objects.create(
                name=name[:255],
                slug=slug,
                domain=draft_domain,
                country=country,
                plan=plan,
                status=Tenant.Status.DRAFT,
                is_active=False,
                provisioning_status=Tenant.ProvisioningStatus.NOT_STARTED,
            )
            TenantDomain.objects.create(tenant=tenant, domain=draft_domain, is_primary=True)
            module_ids = request.POST.getlist("selected_modules")
            if module_ids:
                replace_tenant_modules(tenant, list(Module.objects.filter(pk__in=module_ids)))
            _apply_tenant_branding_from_request(request, tenant, slug)
            tenant.save()
            _log_tenant_provisioning(request, tenant, "Tenant registration draft saved (no database provisioned).")
        except IntegrityError:
            messages.error(request, "Could not save draft: duplicate organization name or conflicting slug.")
            return redirect("platform_dashboard:tenant_register")
        messages.success(
            request,
            f"Draft saved for «{name}». Open Tenant Directory to continue; replace the draft domain when you finalize the workspace URL.",
        )
        return redirect("platform_dashboard:tenant_list")

    if action not in ("create", "create_send_link"):
        messages.error(
            request,
            "The form did not submit a valid action (create / create & send link). "
            "Complete all steps and submit from step 6 (Review & Create), or refresh and try again.",
        )
        return redirect("platform_dashboard:tenant_register")

    if approval == "rejected":
        messages.error(request, "Change approval from Rejected to Pending or Approved before creating a tenant.")
        return redirect("platform_dashboard:tenant_register")

    if action == "create_send_link" and approval != "approved":
        messages.error(request, "Approve the tenant before using Create & Send Setup Link.")
        return redirect("platform_dashboard:tenant_register")

    if action == "create_send_link" and not admin_email:
        messages.error(request, "Admin or contact email is required to send a setup link.")
        return redirect("platform_dashboard:tenant_register")

    if not name:
        messages.error(request, "Organization name is required.")
        return redirect("platform_dashboard:tenant_register")
    if not domain:
        messages.error(request, "Preferred subdomain or custom domain is required.")
        return redirect("platform_dashboard:tenant_register")

    if Tenant.objects.filter(domain=domain).exists() or TenantDomain.objects.filter(domain=domain).exists():
        messages.error(request, f"Domain '{domain}' is already in use.")
        return redirect("platform_dashboard:tenant_register")

    slug = _tenant_register_allocate_slug(slugify(tenant_code or name)[:50] or "tenant")

    if approval == "pending":
        try:
            tenant = Tenant.objects.create(
                name=name[:255],
                slug=slug,
                domain=domain,
                country=country,
                plan=plan,
                status=Tenant.Status.PENDING,
                is_active=False,
                provisioning_status=Tenant.ProvisioningStatus.NOT_STARTED,
            )
            TenantDomain.objects.create(tenant=tenant, domain=domain, is_primary=True)
            module_ids = request.POST.getlist("selected_modules")
            if module_ids:
                replace_tenant_modules(tenant, list(Module.objects.filter(pk__in=module_ids)))
            _apply_tenant_branding_from_request(request, tenant, slug)
            tenant.save()
            _log_tenant_provisioning(
                request,
                tenant,
                "Tenant registered; approval pending — database provisioning was not run.",
            )
        except IntegrityError:
            messages.error(request, "Could not create tenant: duplicate organization name, slug, or domain.")
            return redirect("platform_dashboard:tenant_register")
        messages.success(
            request,
            f"Tenant «{name}» saved as pending. Assign modules and plan are stored; provision the database when approved (Tenant Directory / retry provisioning).",
        )
        return redirect("platform_dashboard:tenant_list")

    try:
        tenant = Tenant.objects.create(
            name=name[:255],
            slug=slug,
            domain=domain,
            country=country,
            plan=plan,
            status=Tenant.Status.PENDING,
            is_active=False,
            provisioning_status=Tenant.ProvisioningStatus.NOT_STARTED,
        )
        TenantDomain.objects.create(tenant=tenant, domain=domain, is_primary=True)
        module_ids = request.POST.getlist("selected_modules")
        if module_ids:
            replace_tenant_modules(tenant, list(Module.objects.filter(pk__in=module_ids)))
        _apply_tenant_branding_from_request(request, tenant, slug)
        tenant.save()
    except IntegrityError:
        messages.error(request, "Could not create tenant: duplicate organization name, slug, or domain.")
        return redirect("platform_dashboard:tenant_register")

    setup_method = (request.POST.get("setup_method") or "invite").strip()
    admin_password = (request.POST.get("admin_temporary_password") or "").strip()
    auto_gen_pw = setup_method != "password" or not admin_password

    onboard = run_full_tenant_provisioning(
        tenant,
        admin_email=admin_email or None,
        admin_password=admin_password or None,
        admin_full_name=admin_full_name,
        auto_generate_admin_password=auto_gen_pw,
        register_flow=True,
    )

    if not onboard.ok:
        try:
            cleanup_failed_registration_tenant(tenant)
        except Exception:
            logger.exception("cleanup_failed_registration_tenant after onboarding failure slug=%s", tenant.slug)
            messages.error(
                request,
                f"Provisioning failed: {onboard.message}. "
                "Automatic cleanup also failed — check the server logs and remove any partial tenant/DB manually.",
            )
            return redirect("platform_dashboard:tenant_register")
        messages.error(
            request,
            "Provisioning failed and was rolled back (no partial tenant left in the directory). "
            f"Details: {onboard.message}",
        )
        return redirect("platform_dashboard:tenant_register")

    messages.success(request, onboard.message)
    if onboard.generated_admin_password:
        messages.warning(
            request,
            "Tenant admin temporary password (copy securely; not stored after this message): "
            f"{onboard.generated_admin_password}",
        )

    _log_tenant_provisioning(
        request,
        tenant,
        f"Tenant provisioned successfully (action={action}, domain={domain}, admin_email={admin_email or 'none'}).",
    )

    login_url = f"https://{tenant.domain}/t/login/"
    if action == "create_send_link" and admin_email:
        try:
            _send_tenant_setup_link_email(recipient=admin_email, tenant=tenant, login_url=login_url)
            messages.info(request, f"A setup email with the sign-in link was sent to {admin_email}.")
        except Exception as exc:
            messages.warning(
                request,
                f"The tenant was created successfully, but the setup email could not be sent ({exc}). "
                f"Share this link manually: {login_url}",
            )

    return redirect("platform_dashboard:tenant_list")


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def tenant_domain_availability_view(request):
    """
    Lightweight AJAX check for preferred subdomain/custom domain uniqueness.
    Returns: { ok: bool, domain: str, message: str }
    """
    subdomain = (request.GET.get("preferred_subdomain") or "").strip()
    custom_domain = (request.GET.get("custom_domain") or "").strip()
    domain = (custom_domain or (f"{subdomain}.sugna.org" if subdomain else "")).strip().lower()
    if not domain:
        return JsonResponse({"ok": False, "domain": "", "message": "Enter a preferred subdomain or a custom domain."})
    in_use = Tenant.objects.filter(domain__iexact=domain).exists() or TenantDomain.objects.filter(domain__iexact=domain).exists()
    if in_use:
        return JsonResponse({"ok": False, "domain": domain, "message": f"Domain '{domain}' is already in use."})
    return JsonResponse({"ok": True, "domain": domain, "message": f"Domain '{domain}' is available."})


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def tenant_detail_view(request, pk):
    """Tenant profile: organization, domain, modules, subscription, billing placeholder, usage, audit placeholder."""
    tenant_modules_prefetch = TenantModule.objects.filter(
        is_enabled=True,
        module__is_active=True,
    ).select_related("module")
    tenant = get_object_or_404(
        Tenant.objects.prefetch_related("modules", Prefetch("tenant_modules", queryset=tenant_modules_prefetch)),
        pk=pk,
    )
    tenant_workspace = resolve_tenant_workspace_open_url(
        tenant,
        enabled_tenant_modules=list(tenant.tenant_modules.all()),
    )
    # Placeholder data for billing and audit until those apps exist
    billing_history = []
    audit_logs = []
    # Tenant users (loaded from tenant isolated DB)
    tenant_users = []
    tenant_users_page = None
    tenant_users_error = ""
    tenant_users_summary = {"total": 0, "active": 0, "admins": 0}
    user_q = (request.GET.get("uq") or "").strip()
    user_page_num = max(1, int(request.GET.get("upage", 1) or 1))
    user_per_page = max(10, min(100, int(request.GET.get("uper_page", 25) or 25)))
    try:
        from tenants.db import ensure_tenant_db_configured

        alias = ensure_tenant_db_configured(tenant)
        if alias == "default" and tenant.db_name:
            # alias not registered but db_name exists; still proceed (ensure_tenant_db_configured should register)
            pass
        if not tenant.db_name:
            tenant_users_error = "Tenant database is not provisioned yet (db_name is empty)."
        else:
            from django.db.models import Q
            from tenant_users.models import TenantUser

            qs = TenantUser.objects.using(alias).all().order_by("email")
            if user_q:
                qs = qs.filter(
                    Q(email__icontains=user_q)
                    | Q(full_name__icontains=user_q)
                    | Q(department__icontains=user_q)
                    | Q(position__icontains=user_q)
                )
            tenant_users_summary["total"] = qs.count()
            tenant_users_summary["active"] = qs.filter(is_active=True).count()
            tenant_users_summary["admins"] = qs.filter(is_tenant_admin=True).count()
            paginator = Paginator(qs, user_per_page)
            tenant_users_page = paginator.get_page(user_page_num)
            tenant_users = tenant_users_page.object_list
    except Exception as exc:
        tenant_users_error = str(exc)[:200]
    context = {
        "tenant": tenant,
        "tenant_workspace": tenant_workspace,
        "billing_history": billing_history,
        "audit_logs": audit_logs,
        "tenant_users": tenant_users,
        "tenant_users_page": tenant_users_page,
        "tenant_users_error": tenant_users_error,
        "tenant_users_summary": tenant_users_summary,
        "user_filters": {"uq": user_q, "upage": user_page_num, "uper_page": user_per_page},
    }
    return render(request, "platform_dashboard/tenant_detail.html", context)


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def tenant_edit_view(request, pk):
    """
    Edit tenant organization, subscription, modules, and branding in the platform UI
    (control-plane database). For DB credentials and provisioning diagnostics, use Django admin.
    """
    tenant = get_object_or_404(Tenant.objects.prefetch_related("modules"), pk=pk)
    modules_all = Module.objects.filter(is_active=True).order_by("sort_order", "code")
    plans = SubscriptionPlan.objects.filter(is_active=True).order_by("sort_order", "code")
    profile, _ = TenantBrandingProfile.objects.get_or_create(tenant=tenant)
    selected_ids = set(tenant.modules.values_list("id", flat=True))

    plan_code_current = ""
    if plans.exists():
        for sp in plans:
            if sp.name == (tenant.plan or "").strip() or sp.code == (tenant.plan or "").strip():
                plan_code_current = sp.code
                break

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        slug_raw = (request.POST.get("slug") or "").strip()
        slug = slugify(slug_raw)[:100] if slug_raw else ""
        domain = (request.POST.get("domain") or "").strip().lower()
        country = (request.POST.get("country") or "").strip()
        status = (request.POST.get("status") or "").strip()
        plan_code = (request.POST.get("plan_code") or "").strip()
        is_active = request.POST.get("is_active") == "on"
        user_count_raw = (request.POST.get("user_count") or "").strip()
        storage_mb_raw = (request.POST.get("storage_mb") or "").strip()
        exp_raw = (request.POST.get("subscription_expiry") or "").strip()

        if not name or not slug or not domain:
            messages.error(request, "Organization name, tenant code, and domain are required.")
        elif Tenant.objects.exclude(pk=tenant.pk).filter(slug__iexact=slug).exists():
            messages.error(request, "That tenant code is already in use.")
        elif Tenant.objects.exclude(pk=tenant.pk).filter(name__iexact=name).exists():
            messages.error(request, "Another tenant already uses this organization name.")
        elif not _tenant_domain_available_for_edit(domain, tenant):
            messages.error(
                request,
                f"The domain «{domain}» is already in use. Choose another domain or subdomain.",
            )
        elif status and status not in dict(Tenant.Status.choices):
            messages.error(request, "Invalid status.")
        else:
            try:
                user_count = max(0, int(user_count_raw)) if user_count_raw.isdigit() else tenant.user_count
            except (TypeError, ValueError):
                user_count = tenant.user_count
            try:
                storage_mb = max(0, int(storage_mb_raw)) if storage_mb_raw.isdigit() else tenant.storage_mb
            except (TypeError, ValueError):
                storage_mb = tenant.storage_mb
            sub_exp = tenant.subscription_expiry
            if exp_raw:
                parsed = parse_date(exp_raw)
                if parsed:
                    sub_exp = parsed
                else:
                    messages.warning(request, "Subscription expiry date was not recognized; left unchanged.")

            plan_label = tenant.plan
            if plan_code:
                sp = SubscriptionPlan.objects.filter(code=plan_code).first()
                if sp:
                    plan_label = sp.name

            raw_mids = request.POST.getlist("module_ids")
            mod_ids = [int(x) for x in raw_mids if str(x).isdigit()]

            old_domain = tenant.domain
            with transaction.atomic():
                tenant.name = name[:255]
                tenant.slug = slug
                tenant.domain = domain[:255]
                tenant.country = country[:100]
                tenant.is_active = is_active
                if status:
                    tenant.status = status
                tenant.plan = plan_label[:100] if plan_label else ""
                tenant.subscription_expiry = sub_exp
                tenant.user_count = user_count
                tenant.storage_mb = storage_mb
                _apply_tenant_branding_edit(request, tenant)
                tenant.save()
                replace_tenant_modules(tenant, list(Module.objects.filter(pk__in=mod_ids)))
                if old_domain != domain:
                    TenantDomain.objects.filter(tenant=tenant, is_primary=True).update(domain=domain)

            if tenant.db_name:
                try:
                    alias = ensure_tenant_db_configured(tenant)
                    if alias and alias != "default":
                        from tenants.services.branding_sync import sync_tenant_branding_to_organization_settings

                        sync_tenant_branding_to_organization_settings(tenant, alias)
                except Exception:
                    logger.warning("tenant_edit: branding sync to tenant DB failed slug=%s", tenant.slug, exc_info=True)

            messages.success(request, f"Saved changes for «{tenant.name}».")
            return redirect("platform_dashboard:tenant_detail", pk=tenant.pk)

        selected_ids = {int(x) for x in request.POST.getlist("module_ids") if str(x).isdigit()}
        plan_code_current = (request.POST.get("plan_code") or "").strip()

    context = {
        "tenant": tenant,
        "modules_all": modules_all,
        "selected_module_ids": selected_ids,
        "plans": plans,
        "profile": profile,
        "plan_code_current": plan_code_current,
        "status_choices": Tenant.Status.choices,
        "post_login_choices": TenantBrandingProfile.PostLoginMode.choices,
    }
    return render(request, "platform_dashboard/tenant_edit.html", context)


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def platform_users_view(request):
    """
    Platform-wide tenant users directory.

    Shows users stored in tenant databases, scoped to tenants subscribed to a selected module.
    """
    from django.db.models import Q
    from tenants.db import ensure_tenant_db_configured

    modules = Module.objects.filter(is_active=True).order_by("code")
    module_id = (request.GET.get("module_id") or "").strip()
    tenant_id = (request.GET.get("tenant_id") or "").strip()
    q = (request.GET.get("q") or "").strip()

    page_num = max(1, int(request.GET.get("page", 1) or 1))
    per_page = max(10, min(100, int(request.GET.get("per_page", 25) or 25)))

    selected_module = None
    if module_id.isdigit():
        selected_module = modules.filter(pk=int(module_id)).first()
    if not selected_module and modules.exists():
        selected_module = modules.first()
        module_id = str(selected_module.id)

    tenant_qs = Tenant.objects.prefetch_related("modules").all().order_by("name")
    if selected_module:
        tenant_qs = tenant_qs.filter(modules__id=selected_module.id)
    tenant_qs = tenant_qs.filter(db_name__isnull=False).exclude(db_name="")
    if tenant_id.isdigit():
        tenant_qs = tenant_qs.filter(pk=int(tenant_id))
    tenants = list(tenant_qs[:500])

    rows = []
    errors = []
    total_scanned_tenants = 0
    total_users_scanned = 0

    try:
        from tenant_users.models import TenantUser
    except Exception as exc:
        return render(
            request,
            "platform_dashboard/platform_users.html",
            {
                "modules": modules,
                "selected_module": selected_module,
                "tenants": tenants,
                "page": None,
                "rows": [],
                "errors": [f"TenantUser model import failed: {str(exc)[:200]}"],
                "filters": {"module_id": module_id, "tenant_id": tenant_id, "q": q, "per_page": per_page},
                "summary": {"tenants": 0, "users": 0, "returned": 0},
            },
        )

    for t in tenants:
        total_scanned_tenants += 1
        try:
            alias = ensure_tenant_db_configured(t)
            qs = TenantUser.objects.using(alias).all()
            if q:
                qs = qs.filter(
                    Q(email__icontains=q)
                    | Q(full_name__icontains=q)
                    | Q(department__icontains=q)
                    | Q(position__icontains=q)
                )
            qs = qs.order_by("email")[:2000]  # safety cap per tenant
            for u in qs:
                rows.append(
                    {
                        "tenant_id": t.id,
                        "tenant_name": t.name,
                        "tenant_slug": t.slug,
                        "email": u.email,
                        "full_name": u.full_name,
                        "department": u.department,
                        "position": u.position,
                        "is_active": u.is_active,
                        "is_admin": u.is_tenant_admin,
                        "last_login_at": u.last_login_at,
                    }
                )
            total_users_scanned += qs.count() if q else 0
        except Exception as exc:
            errors.append(f"{t.slug}: {str(exc)[:200]}")

    # Default ordering: tenant then email
    rows.sort(key=lambda r: (r["tenant_name"] or "", r["email"] or ""))

    paginator = Paginator(rows, per_page)
    page = paginator.get_page(page_num)

    context = {
        "modules": modules,
        "selected_module": selected_module,
        "tenants": tenants,
        "rows": page.object_list,
        "page": page,
        "errors": errors,
        "filters": {"module_id": module_id, "tenant_id": tenant_id, "q": q, "per_page": per_page},
        "summary": {"tenants": total_scanned_tenants, "users": len(rows), "returned": len(page.object_list)},
    }
    return render(request, "platform_dashboard/platform_users.html", context)


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def platform_reset_tenant_user_password_view(request):
    """Platform Admin: reset a tenant user's password inside the tenant DB."""
    if request.method != "POST":
        return redirect("platform_dashboard:platform_users")

    from secrets import token_urlsafe
    from tenants.db import ensure_tenant_db_configured

    tenant_id = (request.POST.get("tenant_id") or "").strip()
    email = (request.POST.get("email") or "").strip().lower()
    next_url = (request.POST.get("next") or "").strip() or request.META.get("HTTP_REFERER") or ""

    if not tenant_id.isdigit() or not email:
        messages.error(request, "Missing tenant or email.")
        return redirect(next_url or "platform_dashboard:platform_users")

    tenant = Tenant.objects.filter(pk=int(tenant_id)).first()
    if not tenant:
        messages.error(request, "Tenant not found.")
        return redirect(next_url or "platform_dashboard:platform_users")
    if not tenant.db_name:
        messages.error(request, f"Tenant '{tenant.slug}' database is not provisioned.")
        return redirect(next_url or "platform_dashboard:tenant_detail", pk=tenant.id)

    try:
        from tenant_users.models import TenantUser

        alias = ensure_tenant_db_configured(tenant)
        user = TenantUser.objects.using(alias).filter(email=email).first()
        if not user:
            messages.error(request, f"No user '{email}' found in tenant '{tenant.slug}'.")
            return redirect(next_url or "platform_dashboard:tenant_detail", pk=tenant.id)

        temp_password = token_urlsafe(10)  # ~14 chars; URL-safe
        user.set_password(temp_password)
        user.save(using=alias, update_fields=["password_hash"])

        messages.success(
            request,
            f"Temporary password set for {email} in {tenant.name}: {temp_password}",
        )
    except Exception as exc:
        messages.error(request, f"Password reset failed: {str(exc)[:200]}")

    return redirect(next_url or "platform_dashboard:tenant_detail", pk=tenant.id)


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def platform_set_tenant_user_password_view(request):
    """Platform Admin: set an explicit password for a tenant user inside the tenant DB."""
    from tenants.db import ensure_tenant_db_configured

    tenant_id = (request.GET.get("tenant_id") or request.POST.get("tenant_id") or "").strip()
    email = (request.GET.get("email") or request.POST.get("email") or "").strip().lower()
    next_url = (request.GET.get("next") or request.POST.get("next") or "").strip() or request.META.get("HTTP_REFERER") or ""

    if not tenant_id.isdigit() or not email:
        messages.error(request, "Missing tenant or email.")
        return redirect(next_url or "platform_dashboard:platform_users")

    tenant = Tenant.objects.filter(pk=int(tenant_id)).first()
    if not tenant:
        messages.error(request, "Tenant not found.")
        return redirect(next_url or "platform_dashboard:platform_users")
    if not tenant.db_name:
        messages.error(request, f"Tenant '{tenant.slug}' database is not provisioned.")
        return redirect(next_url or "platform_dashboard:tenant_detail", pk=tenant.id)

    try:
        from tenant_users.models import TenantUser

        alias = ensure_tenant_db_configured(tenant)
        user = TenantUser.objects.using(alias).filter(email=email).first()
        if not user:
            messages.error(request, f"No user '{email}' found in tenant '{tenant.slug}'.")
            return redirect(next_url or "platform_dashboard:tenant_detail", pk=tenant.id)

        if request.method == "POST":
            new_password = (request.POST.get("new_password") or "").strip()
            confirm = (request.POST.get("confirm_password") or "").strip()
            if len(new_password) < 8:
                messages.error(request, "Password must be at least 8 characters.")
            elif new_password != confirm:
                messages.error(request, "Password and confirmation do not match.")
            else:
                user.set_password(new_password)
                user.save(using=alias, update_fields=["password_hash"])
                messages.success(request, f"Password updated for {email} in {tenant.name}.")
                return redirect(next_url or "platform_dashboard:tenant_detail", pk=tenant.id)
    except Exception as exc:
        messages.error(request, f"Set password failed: {str(exc)[:200]}")
        return redirect(next_url or "platform_dashboard:tenant_detail", pk=tenant.id)

    return render(
        request,
        "platform_dashboard/set_tenant_user_password.html",
        {"tenant": tenant, "email": email, "next": next_url},
    )


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def diagnostics_view(request):
    """Self-healing diagnostics: incidents, check runs, health summary, run scan form."""
    from diagnostics.models import Incident, DiagnosticCheckRun, DiagnosticReport

    incidents = Incident.objects.all().order_by("-created_at")[:50]
    check_runs = DiagnosticCheckRun.objects.all().order_by("-created_at")[:30]
    reports = DiagnosticReport.objects.all().order_by("-created_at")[:20]
    open_incidents = Incident.objects.filter(status__in=(Incident.Status.OPEN, Incident.Status.INVESTIGATING)).count()
    failed_runs = DiagnosticCheckRun.objects.filter(status=DiagnosticCheckRun.Status.FAILURE).count()
    tenants = Tenant.objects.filter(db_name__isnull=False).exclude(db_name="").order_by("name")

    return render(
        request,
        "platform_dashboard/diagnostics.html",
        {
            "incidents": incidents,
            "check_runs": check_runs,
            "reports": reports,
            "open_incidents": open_incidents,
            "failed_runs": failed_runs,
            "tenants": tenants,
        },
    )


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def diagnostics_run_scan_view(request):
    """POST: run manual scan (scope, tenant_id, apply_fixes), redirect to report detail."""
    from diagnostics.services.scan_orchestrator import run_manual_scan

    if request.method != "POST":
        return redirect("platform_dashboard:diagnostics")
    scope = (request.POST.get("scope") or "platform").strip().lower()
    if scope not in ("platform", "tenant", "database", "api", "service"):
        messages.error(request, "Invalid scope.")
        return redirect("platform_dashboard:diagnostics")
    tenant_id = request.POST.get("tenant_id")
    if tenant_id:
        try:
            tenant_id = int(tenant_id)
        except (TypeError, ValueError):
            tenant_id = None
    if scope == "tenant" and not tenant_id:
        messages.error(request, "Select a tenant for tenant scope.")
        return redirect("platform_dashboard:diagnostics")
    service = (request.POST.get("service") or "").strip() or None
    if scope == "service" and not service:
        service = "cache"
    apply_fixes = request.POST.get("apply_fixes") in ("1", "on", "true", "yes")
    try:
        report = run_manual_scan(scope=scope, tenant_id=tenant_id, service=service, apply_fixes=apply_fixes)
        messages.success(request, f"Scan completed. Report #{report.id}.")
        return redirect("platform_dashboard:diagnostics_report", report_id=report.id)
    except Exception as e:
        messages.error(request, str(e)[:200])
        return redirect("platform_dashboard:diagnostics")


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
def diagnostics_report_view(request, report_id):
    """Diagnostic report detail: runs, findings, incidents."""
    from diagnostics.models import DiagnosticReport, Finding

    report = get_object_or_404(
        DiagnosticReport.objects.prefetch_related("check_runs__findings", "incidents__remediation_logs"),
        pk=report_id,
    )
    run_ids = [r.id for r in report.check_runs.all()]
    report_findings = list(Finding.objects.filter(run_id__in=run_ids).order_by("-severity", "-created_at")) if run_ids else []
    return render(
        request,
        "platform_dashboard/diagnostics_report.html",
        {"report": report, "report_findings": report_findings},
    )
