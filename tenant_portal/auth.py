from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.http import HttpRequest

from tenants.db import ensure_tenant_db_configured, tenant_db_alias
from sugna_core.tenant_context import get_current_tenant


SESSION_KEY = "tenant_user_id"


@dataclass(frozen=True)
class TenantAuthContext:
    tenant_db: str
    user_id: int


def get_tenant_db_for_request(request: HttpRequest) -> Optional[str]:
    tenant = getattr(request, "tenant", None) or get_current_tenant()
    if not tenant or not getattr(tenant, "db_name", None):
        return None
    ensure_tenant_db_configured(tenant)
    return tenant_db_alias(tenant)


def tenant_login(request: HttpRequest, user_id: int) -> None:
    request.session[SESSION_KEY] = int(user_id)


def tenant_logout(request: HttpRequest) -> None:
    request.session.pop(SESSION_KEY, None)


def get_tenant_user(request: HttpRequest):
    from tenant_users.models import TenantUser

    user_id = request.session.get(SESSION_KEY)
    tenant_db = get_tenant_db_for_request(request)
    if not user_id or not tenant_db:
        return None
    return TenantUser.objects.using(tenant_db).filter(pk=user_id, is_active=True).first()

