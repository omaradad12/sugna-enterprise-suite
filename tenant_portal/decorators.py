from __future__ import annotations

from functools import wraps
from typing import Callable, Sequence

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from tenant_portal.auth import get_tenant_db_for_request, get_tenant_user, redirect_to_tenant_login
from rbac.models import user_has_permission


def tenant_view(
    require_module: str | None = None,
    require_perm: str | None = None,
    require_perm_any: Sequence[str] | None = None,
):
    """
    Decorator for tenant-scoped views:
    - tenant resolved (request.tenant)
    - tenant DB provisioned
    - tenant user logged in
    - optional module entitlement (control plane; respects TenantModule.is_enabled)
    - optional RBAC permission (tenant DB), or any-of list via require_perm_any
    """

    def decorator(view_func: Callable[[HttpRequest], HttpResponse]):
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args, **kwargs):
            tenant = getattr(request, "tenant", None)
            if not tenant:
                return render(request, "tenant_portal/tenant_missing.html", status=404)

            tenant_db = get_tenant_db_for_request(request)
            if not tenant_db:
                return render(request, "tenant_portal/tenant_not_provisioned.html", {"tenant": tenant}, status=503)

            user = get_tenant_user(request)
            if not user:
                return redirect_to_tenant_login(request)

            # Provide consistent attributes even if middleware isn't installed.
            request.tenant_db = tenant_db
            request.tenant_user = user

            if require_module:
                from tenants.services.tenant_modules import tenant_enabled_module_codes

                if require_module not in tenant_enabled_module_codes(tenant):
                    return render(
                        request,
                        "tenant_portal/forbidden.html",
                        {"tenant": tenant, "tenant_user": user, "reason": "Module is not enabled for this tenant."},
                        status=403,
                    )

            perm_list: list[str] = []
            if require_perm_any:
                perm_list = [p for p in require_perm_any if p]
            elif require_perm:
                perm_list = [require_perm]

            if perm_list:
                cached = getattr(request, "rbac_permission_codes", None)
                allowed = False
                if isinstance(cached, set) and "*" in cached:
                    allowed = True
                elif isinstance(cached, set):
                    allowed = any(p in cached for p in perm_list)
                if not allowed:
                    allowed = any(user_has_permission(user, p, using=tenant_db) for p in perm_list)
                if not allowed:
                    return render(
                        request,
                        "tenant_portal/forbidden.html",
                        {
                            "tenant": tenant,
                            "tenant_user": user,
                            "reason": "You do not have permission to access this page.",
                        },
                        status=403,
                    )

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator

