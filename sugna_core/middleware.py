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

        host = (request.get_host() or "").split(":")[0].lower().strip()

        tenant = None
        if host and host not in {"127.0.0.1", "localhost"}:
            tenant = TenantDomain.objects.select_related("tenant").filter(domain=host).values_list("tenant", flat=True).first()
            if tenant:
                tenant = Tenant.objects.filter(pk=tenant).first()
            if not tenant:
                tenant = Tenant.objects.filter(domain=host).first()

        request.tenant = tenant
        set_current_tenant(tenant)

        if tenant:
            ensure_tenant_db_configured(tenant)

        try:
            return self.get_response(request)
        finally:
            set_current_tenant(None)
