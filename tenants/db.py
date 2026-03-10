from __future__ import annotations

from django.conf import settings


def tenant_db_alias(tenant) -> str:
    return f"tenant_{tenant.slug}"


def ensure_tenant_db_configured(tenant) -> str:
    """
    Ensure a DATABASES entry exists for this tenant and return its alias.

    This does not open connections; it only registers connection parameters.
    If db_name is not configured yet, it returns 'default' to keep dev flows working.
    """
    if not getattr(tenant, "db_name", None):
        return "default"

    alias = tenant_db_alias(tenant)
    if alias in settings.DATABASES:
        return alias

    base = settings.DATABASES["default"].copy()
    base.update(
        {
            "NAME": tenant.db_name,
            "USER": tenant.db_user or base.get("USER"),
            "PASSWORD": tenant.db_password or base.get("PASSWORD"),
            "HOST": tenant.db_host or base.get("HOST"),
            "PORT": tenant.db_port or base.get("PORT"),
        }
    )
    settings.DATABASES[alias] = base
    return alias

