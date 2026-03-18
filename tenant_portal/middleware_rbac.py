from __future__ import annotations

from typing import Callable, Iterable

from django.http import HttpRequest, HttpResponse

from tenant_portal.auth import get_tenant_db_for_request, get_tenant_user


class RBACContextMiddleware:
    """
    Build a fast per-request RBAC context:
    - resolves tenant_db and tenant_user (if available)
    - caches permission codes for membership checks
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Only tenant portal routes require tenant-scoped RBAC.
        if not (request.path or "").startswith("/t/"):
            return self.get_response(request)

        tenant = getattr(request, "tenant", None)
        if not tenant:
            return self.get_response(request)

        tenant_db = get_tenant_db_for_request(request)
        if not tenant_db:
            return self.get_response(request)

        user = get_tenant_user(request)
        if not user:
            return self.get_response(request)

        request.tenant_db = tenant_db
        request.tenant_user = user

        try:
            from rbac.models import RolePermission

            codes: Iterable[str] = (
                RolePermission.objects.using(tenant_db)
                .filter(role__role_users__user_id=user.id)
                .values_list("permission__code", flat=True)
                .distinct()
            )
            request.rbac_permission_codes = set(codes)
        except Exception:
            request.rbac_permission_codes = set()

        return self.get_response(request)

