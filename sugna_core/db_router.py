from __future__ import annotations

from django.conf import settings

from sugna_core.tenant_context import get_current_tenant
from tenants.db import ensure_tenant_db_configured


class TenantDatabaseRouter:
    """
    Routes models for tenant-scoped apps to the current tenant database.

    This is intentionally conservative: only app labels listed in TENANT_APP_LABELS
    will be routed to tenant DBs. Everything else stays in the control-plane DB.
    """

    def _tenant_alias(self) -> str | None:
        tenant = get_current_tenant()
        if not tenant:
            return None
        return ensure_tenant_db_configured(tenant)

    def db_for_read(self, model, **hints):
        if model._meta.app_label in getattr(settings, "TENANT_APP_LABELS", []):
            return self._tenant_alias() or "default"
        return "default"

    def db_for_write(self, model, **hints):
        if model._meta.app_label in getattr(settings, "TENANT_APP_LABELS", []):
            return self._tenant_alias() or "default"
        return "default"

    def allow_relation(self, obj1, obj2, **hints):
        tenant_apps = set(getattr(settings, "TENANT_APP_LABELS", []))
        a1 = obj1._meta.app_label in tenant_apps
        a2 = obj2._meta.app_label in tenant_apps
        if a1 != a2:
            return False
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        tenant_apps = set(getattr(settings, "TENANT_APP_LABELS", []))
        if app_label in tenant_apps:
            if db == "default":
                return False
            return True
        # Control-plane apps
        return db == "default"

