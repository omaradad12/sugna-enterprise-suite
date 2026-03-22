import csv
import json
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
from django.db.models import Count, Q
from django.db import IntegrityError, utils as db_utils
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify

from tenants.branding import extract_brand_colors
from tenants.db import ensure_tenant_db_configured
from tenants.models import Module, SubscriptionPlan, Tenant, TenantDomain
from tenants.services.onboarding import run_full_tenant_provisioning
from tenants.services.registration_cleanup import cleanup_failed_registration_tenant
from tenants.services.tenant_modules import replace_tenant_modules


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
    modules = (
        Module.objects.all()
        .annotate(tenant_count=Count("tenants"))
        .order_by("code")
    )
    return render(request, "platform_dashboard/module_list.html", {"modules": modules})


@login_required(login_url="/platform/login/")
@staff_member_required(login_url="/platform/login/")
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

        module_path_map = {
            "finance": "/t/finance/",
            "grants": "/t/grants/",
            "integrations": "/t/integrations/",
            # Audit & Risk workplace (tenant portal) lives under /t/audit-risk/
            "audit_risk": "/t/audit-risk/",
        }
        path = module_path_map.get(module.code, "/t/")

        # For preview, always open on the current host/port instead of tenant.domain
        host = request.get_host()
        target = f"http://{host}{path}"
        return HttpResponseRedirect(target)

    context = {
        "modules": modules,
        "tenants": tenants,
        "selected_code": selected_code,
    }
    return render(request, "platform_dashboard/module_workplace_preview.html", context)


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
    logo_file = request.FILES.get("logo")
    if logo_file:
        ext = os.path.splitext(logo_file.name)[1] or ".png"
        relative_path = f"tenant_logos/{slug}{ext}"
        saved_path = default_storage.save(relative_path, logo_file)
        tenant.brand_logo_url = settings.MEDIA_URL + saved_path.replace("\\", "/")
        primary, bg = extract_brand_colors(default_storage.open(saved_path, "rb"))
        if primary and not tenant.brand_primary_color:
            tenant.brand_primary_color = primary
        if bg and not tenant.brand_background_color:
            tenant.brand_background_color = bg
    brand_primary = (request.POST.get("brand_primary_color") or "").strip()
    brand_bg = (request.POST.get("brand_secondary_color") or "").strip()
    if brand_primary:
        tenant.brand_primary_color = brand_primary
    if brand_bg:
        tenant.brand_background_color = brand_bg
    if not tenant.brand_login_title:
        tenant.brand_login_title = tenant.name


def _log_tenant_provisioning(request, tenant: Tenant, message: str) -> None:
    from django.contrib.admin.models import ADDITION, LogEntry
    from django.contrib.contenttypes.models import ContentType

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return
    LogEntry.objects.create(
        user_id=user.pk,
        content_type_id=ContentType.objects.get_for_model(Tenant).pk,
        object_id=str(tenant.pk),
        object_repr=str(tenant)[:200],
        action_flag=ADDITION,
        change_message=message[:2000],
    )


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
        return render(
            request,
            "platform_dashboard/tenant_register.html",
            {"modules": modules, "subscription_plans": subscription_plans},
        )

    action = request.POST.get("action", "create")
    approval = (request.POST.get("approval_decision") or "pending").strip().lower()

    name = (request.POST.get("organization_legal_name") or request.POST.get("organization_short_name") or "").strip()
    tenant_code = (request.POST.get("tenant_code") or "").strip()
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

    if Tenant.objects.filter(domain=domain).exists():
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
        cleanup_failed_registration_tenant(tenant)
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
def tenant_detail_view(request, pk):
    """Tenant profile: organization, domain, modules, subscription, billing placeholder, usage, audit placeholder."""
    tenant = get_object_or_404(Tenant.objects.prefetch_related("modules"), pk=pk)
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
def module_list_view(request):
    """Module list in platform design."""
    modules = Module.objects.annotate(tenant_count=Count("tenants")).order_by("code")
    return render(request, "platform_dashboard/module_list.html", {"modules": modules})


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
