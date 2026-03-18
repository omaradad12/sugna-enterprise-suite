from __future__ import annotations

from functools import wraps
from typing import Callable

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from tenant_portal.auth import get_tenant_db_for_request, get_tenant_user
from rbac.models import user_has_permission


def tenant_view(require_module: str | None = None, require_perm: str | None = None):
    """
    Decorator for tenant-scoped views:
    - tenant resolved (request.tenant)
    - tenant DB provisioned
    - tenant user logged in
    - optional module entitlement (control plane)
    - optional RBAC permission (tenant DB)
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
                return redirect(reverse("tenant_portal:login"))

            # Provide consistent attributes even if middleware isn't installed.
            request.tenant_db = tenant_db
            request.tenant_user = user

            if require_module:
                enabled = set(tenant.modules.values_list("code", flat=True))
                if require_module not in enabled:
                    return render(
                        request,
                        "tenant_portal/forbidden.html",
                        {"tenant": tenant, "tenant_user": user, "reason": "Module is not enabled for this tenant."},
                        status=403,
                    )

            if require_perm:
                cached = getattr(request, "rbac_permission_codes", None)
                allowed = False
                if isinstance(cached, set):
                    allowed = ("*" in cached) or (require_perm in cached)
                if not allowed and user_has_permission(user, require_perm, using=tenant_db):
                    allowed = True
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

