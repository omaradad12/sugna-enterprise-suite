from django.conf import settings

"""
Redirect staff users from Django admin index to the enterprise Platform Dashboard.
Keeps /admin/tenants/..., /admin/auth/... etc. unchanged for CRUD.
"""


class RedirectAdminIndexToPlatformMiddleware:
    """Send staff users from /admin/ to /platform/ so they see the enterprise UI first."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.path.rstrip("/") == "/admin"
            and request.user.is_authenticated
            and getattr(request.user, "is_staff", False)
        ):
            from django.shortcuts import redirect
            return redirect("/platform/")
        return self.get_response(request)


class TenantResolutionMiddleware:
    """
    Resolve the tenant from the request host and attach it to request.tenant.

    - Control plane routes (/platform/, /admin/, APIs) can still operate without a tenant.
    - In production, you can tighten this to "fail closed" for tenant routes.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from tenants.models import Tenant, TenantDomain
        from tenants.db import ensure_tenant_db_configured
        from sugna_core.tenant_context import set_current_tenant

        # Control-plane and public marketing routes (/, /about/, /modules/, …), plus
        # /platform/, /admin/, /api/..., should not depend on tenant resolution.
        # Tenant-aware application routes are under `/t/`.
        path = (request.path or "").rstrip("/")
        if not path.startswith("/t/") and path != "/t":
            request.tenant = None
            set_current_tenant(None)
            return self.get_response(request)

        host = (request.get_host() or "").split(":")[0].lower().strip()

        tenant = None
        # Legacy first-segment names under /t/ that are not tenant slugs (flat URLs).
        _legacy_t_root = {
            "login",
            "logout",
            "profile",
            "settings",
            "portal",
            "hospital",
            "finance",
            "integrations",
            "audit-risk",
            "recv",
            "pay",
            "governance",
            "documents",
            "grants",
            "cashbook",
            "cashbank",
            "media",
            "customer-portal",
            "draft-excel",
        }
        path_parts = [p for p in path.split("/") if p]
        # /t/<tenant_slug>/… → set tenant and rewrite PATH_INFO to /t/… so existing routes work.
        if len(path_parts) >= 2 and path_parts[0] == "t":
            slug_candidate = path_parts[1]
            if slug_candidate not in _legacy_t_root:
                t_by_slug = (
                    Tenant.objects.filter(slug=slug_candidate)
                    .defer("trial_started_at", "trial_converted_at")
                    .first()
                )
                if t_by_slug:
                    tenant = t_by_slug
                    rest_parts = path_parts[2:]
                    new_tail = "/".join(rest_parts) if rest_parts else ""
                    new_path = ("/t/" + new_tail) if new_tail else "/t/"
                    if new_tail and not new_path.endswith("/"):
                        new_path += "/"
                    # WSGIRequest keeps path, path_info, and META["PATH_INFO"] in sync; mirror that
                    # so resolvers and CommonMiddleware see the inner /t/… route.
                    request.path_info = new_path
                    request.META["PATH_INFO"] = new_path
                    script_name = request.META.get("SCRIPT_NAME", "") or ""
                    request.path = "%s/%s" % (
                        script_name.rstrip("/"),
                        new_path.replace("/", "", 1),
                    )

        if host and tenant is None:
            tenant_id = (
                TenantDomain.objects.select_related("tenant")
                .filter(domain=host)
                .values_list("tenant", flat=True)
                .first()
            )
            if tenant_id:
                tenant = (
                    Tenant.objects.filter(pk=tenant_id)
                    .defer("trial_started_at", "trial_converted_at")
                    .first()
                )
            if not tenant:
                tenant = (
                    Tenant.objects.filter(domain=host)
                    .defer("trial_started_at", "trial_converted_at")
                    .first()
                )

        # Developer-friendly fallback: when running locally with DEBUG on and no
        # explicit domain match, route localhost to the first active tenant so
        # paths like /t/finance/ work without DNS / host headers.
        if not tenant and settings.DEBUG and host in {"127.0.0.1", "localhost"}:
            tenant = (
                Tenant.objects.filter(is_active=True)
                .defer("trial_started_at", "trial_converted_at")
                .order_by("id")
                .first()
            )

        request.tenant = tenant
        set_current_tenant(tenant)

        if tenant:
            ensure_tenant_db_configured(tenant)

        try:
            return self.get_response(request)
        finally:
            set_current_tenant(None)
