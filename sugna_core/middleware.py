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

        # Control-plane and other non-tenant routes (e.g. /platform/, /admin/, /api/...)
        # should not depend on tenant resolution or tenant DB provisioning.
        # Tenant-aware routes are under `/t/`.
        path = (request.path or "").rstrip("/")
        if not path.startswith("/t/") and path != "/t":
            request.tenant = None
            set_current_tenant(None)
            return self.get_response(request)

        host = (request.get_host() or "").split(":")[0].lower().strip()

        tenant = None
        if host:
            tenant_id = (
                TenantDomain.objects.select_related("tenant")
                .filter(domain=host)
                .values_list("tenant", flat=True)
                .first()
            )
            if tenant_id:
                tenant = Tenant.objects.filter(pk=tenant_id).first()
            if not tenant:
                tenant = Tenant.objects.filter(domain=host).first()

        # Developer-friendly fallback: when running locally with DEBUG on and no
        # explicit domain match, route localhost to the first active tenant so
        # paths like /t/finance/ work without DNS / host headers.
        if not tenant and settings.DEBUG and host in {"127.0.0.1", "localhost"}:
            tenant = Tenant.objects.filter(is_active=True).order_by("id").first()

        request.tenant = tenant
        set_current_tenant(tenant)

        if tenant:
            ensure_tenant_db_configured(tenant)

        try:
            return self.get_response(request)
        finally:
            set_current_tenant(None)
