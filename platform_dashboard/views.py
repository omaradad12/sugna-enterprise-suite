import csv
import json
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.db.models import Count, Q
from django.core.paginator import Paginator
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib import messages
from tenants.models import Tenant, Module
from django.core.files.storage import default_storage
from django.utils.text import slugify
import os

from tenants.branding import extract_brand_colors


def logo_view(request):
    """Serve the Sugna logo image so it loads regardless of static files config."""
    logo_path = Path(settings.BASE_DIR) / "platform_dashboard" / "static" / "platform_dashboard" / "images" / "sugna-logo.png"
    if not logo_path.exists():
        return HttpResponse(status=404)
    with open(logo_path, "rb") as f:
        return HttpResponse(f.read(), content_type="image/png")


@login_required
@staff_member_required
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
    module_stats = list(
        Module.objects.filter(is_active=True)
        .annotate(tenant_count=Count("tenants"))
        .values_list("name", "tenant_count")
        .order_by("-tenant_count")[:8]
    )
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


@login_required
@staff_member_required
def module_list_view(request):
    """List all modules with counts."""
    modules = (
        Module.objects.all()
        .annotate(tenant_count=Count("tenants"))
        .order_by("code")
    )
    return render(request, "platform_dashboard/module_list.html", {"modules": modules})


@login_required
@staff_member_required
def module_workplace_preview_view(request):
    """
    Let platform admin choose a module + tenant and open that tenant's module dashboard.
    This is a design/preview tool; it just redirects the browser to the tenant URL.
    """
    all_modules = list(Module.objects.filter(is_active=True).order_by("code"))
    selected_code = request.GET.get("module") or (all_modules[0].code if all_modules else "")

    # For this screen we lock to the selected module (no switching between modules here).
    modules = [m for m in all_modules if m.code == selected_code] if selected_code else all_modules

    tenants_qs = Tenant.objects.all()
    if selected_code:
        tenants_qs = tenants_qs.filter(modules__code=selected_code)
    tenants = tenants_qs.order_by("name").distinct()

    if request.method == "POST":
        module_code = request.POST.get("module_code") or ""
        tenant_id = request.POST.get("tenant_id") or ""

        tenant = Tenant.objects.filter(pk=tenant_id).first()
        module = Module.objects.filter(code=module_code).first()

        if not tenant or not module:
            messages.error(request, "Please select a valid module and tenant.")
            return redirect("platform_dashboard:module_workplace_preview")

        if not tenant.domain:
            messages.error(request, "Selected tenant has no domain configured.")
            return redirect(f"{reverse('platform_dashboard:module_workplace_preview')}?module={module.code}")

        module_path_map = {
            "finance": "/t/finance/",
            "grants": "/t/grants/",
            "integrations": "/t/integrations/",
        }
        path = module_path_map.get(module.code, "/t/")

        target = f"http://{tenant.domain}:8000{path}"
        return HttpResponseRedirect(target)

    context = {
        "modules": modules,
        "tenants": tenants,
        "selected_code": selected_code,
    }
    return render(request, "platform_dashboard/module_workplace_preview.html", context)


@login_required
@staff_member_required
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

    qs = Tenant.objects.prefetch_related("modules").all()

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


@login_required
@staff_member_required
def tenant_register_view(request):
    """Tenant registration form (GET) and create tenant (POST). Maps form fields to Tenant where applicable."""
    modules = Module.objects.filter(is_active=True).order_by("code")
    if request.method == "POST":
        action = request.POST.get("action", "create")
        name = (request.POST.get("organization_legal_name") or request.POST.get("organization_short_name") or "").strip()
        tenant_code = (request.POST.get("tenant_code") or "").strip()
        subdomain = (request.POST.get("preferred_subdomain") or "").strip()
        custom_domain = (request.POST.get("custom_domain") or "").strip()
        domain = (custom_domain or (subdomain + ".sugna.org") if subdomain else "").strip()
        country = (request.POST.get("country") or "").strip()
        plan = (request.POST.get("plan_name") or "").strip()
        if action == "draft":
            messages.info(request, "Draft not persisted yet. Use Create Tenant to save.")
            return redirect("platform_dashboard:tenant_register")
        if not name:
            messages.error(request, "Organization name is required.")
        elif not domain:
            messages.error(request, "Preferred subdomain or custom domain is required.")
        else:
            slug = slugify(tenant_code or name)[:50] or "tenant"
            if Tenant.objects.filter(slug=slug).exists():
                base, i = slug, 1
                while Tenant.objects.filter(slug=slug).exists():
                    slug = f"{base}-{i}"
                    i += 1
            if Tenant.objects.filter(domain=domain).exists():
                messages.error(request, f"Domain '{domain}' is already in use.")
            else:
                tenant = Tenant.objects.create(
                    name=name,
                    slug=slug,
                    domain=domain,
                    country=country,
                    plan=plan,
                    status=Tenant.Status.PENDING,
                    is_active=False,
                )
                module_ids = request.POST.getlist("selected_modules")
                if module_ids:
                    tenant.modules.set(Module.objects.filter(pk__in=module_ids))
                # Handle branding fields (colors) and logo upload
                logo_file = request.FILES.get("logo")
                if logo_file:
                    ext = os.path.splitext(logo_file.name)[1] or ".png"
                    relative_path = f"tenant_logos/{slug}{ext}"
                    saved_path = default_storage.save(relative_path, logo_file)
                    from django.conf import settings

                    tenant.brand_logo_url = settings.MEDIA_URL + saved_path.replace("\\", "/")

                    # Auto-derive branding colors from the logo if not explicitly provided.
                    primary, bg = extract_brand_colors(default_storage.open(saved_path, "rb"))
                    if primary and not tenant.brand_primary_color:
                        tenant.brand_primary_color = primary
                    if bg and not tenant.brand_background_color:
                        tenant.brand_background_color = bg

                # If colors were explicitly chosen in the form, they take precedence.
                brand_primary = (request.POST.get("brand_primary_color") or "").strip()
                brand_bg = (request.POST.get("brand_secondary_color") or "").strip()
                if brand_primary:
                    tenant.brand_primary_color = brand_primary
                if brand_bg:
                    tenant.brand_background_color = brand_bg

                # Default login title/subtitle from tenant name if not customized later.
                if not tenant.brand_login_title:
                    tenant.brand_login_title = tenant.name

                tenant.save()
                if action == "create_send_link":
                    messages.success(request, f"Tenant «{name}» created. Setup link can be sent when email is configured.")
                else:
                    messages.success(request, f"Tenant «{name}» created successfully.")
                return redirect("platform_dashboard:tenant_detail", pk=tenant.pk)
        return redirect("platform_dashboard:tenant_register")
    return render(request, "platform_dashboard/tenant_register.html", {"modules": modules})


@login_required
@staff_member_required
def tenant_detail_view(request, pk):
    """Tenant profile: organization, domain, modules, subscription, billing placeholder, usage, audit placeholder."""
    tenant = get_object_or_404(Tenant.objects.prefetch_related("modules"), pk=pk)
    # Placeholder data for billing and audit until those apps exist
    billing_history = []
    audit_logs = []
    context = {
        "tenant": tenant,
        "billing_history": billing_history,
        "audit_logs": audit_logs,
    }
    return render(request, "platform_dashboard/tenant_detail.html", context)


@login_required
@staff_member_required
def module_list_view(request):
    """Module list in platform design."""
    modules = Module.objects.annotate(tenant_count=Count("tenants")).order_by("code")
    return render(request, "platform_dashboard/module_list.html", {"modules": modules})
