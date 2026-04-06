"""
Module workplace path helpers (Platform → tenant deep links).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.utils import timezone

if TYPE_CHECKING:
    from tenants.models import Module, Tenant, TenantModule

# Relative to /t/ when the request host is already the tenant domain (see TenantResolutionMiddleware).
# When using path-based tenant URLs on a shared host, the platform uses /t/<slug>/ + this path.
TENANT_MODULE_HOME_REL_PATH: dict[str, str] = {
    "finance_grants": "finance/",
    "hospital": "hospital/",
    "audit_risk": "audit-risk/",
    "integrations": "integrations/",
    "procurement": "grants/procurement/",
}

# Named URL names on platform_dashboard for platform-category modules
PLATFORM_MODULE_ROUTE: dict[str, str] = {
    "diagnostics": "platform_dashboard:diagnostics",
    "help_center": "platform_dashboard:help_center",
    "integrations": "platform_dashboard:integrations_hub",
}


def is_platform_module(module: Module) -> bool:
    return (module.category or "").strip().lower() == "platform"


def tenant_module_home_relpath(module_code: str) -> str:
    mapped = TENANT_MODULE_HOME_REL_PATH.get(module_code)
    if mapped is not None:
        return mapped
    safe = module_code.replace("_", "-").strip()
    if not safe:
        return ""
    return f"{safe}/"


def normalize_tenant_workspace_host(domain: str | None) -> str | None:
    """Return a usable hostname for https:// links, or None if clearly invalid."""
    if domain is None:
        return None
    d = domain.strip().lower()
    if not d or ".." in d or "/" in d or " " in d or "\\" in d:
        return None
    return d


def tenant_subscription_allows_workspace(tenant: Tenant) -> tuple[bool, str]:
    """Whether the tenant may open a tenant-app workspace (subscription / lifecycle)."""
    from tenants.models import Tenant as TenantModel

    if not tenant.is_active:
        return False, "Tenant is not active."
    if tenant.status in (
        TenantModel.Status.DRAFT,
        TenantModel.Status.SUSPENDED,
        TenantModel.Status.EXPIRED,
        TenantModel.Status.FAILED,
    ):
        return False, f"Tenant status is {tenant.get_status_display()}."
    if tenant.subscription_expiry and tenant.subscription_expiry < timezone.now().date():
        return False, "Subscription has expired."
    return True, ""


def build_tenant_workspace_public_url(domain: str, path_under_t: str) -> str:
    """
    Absolute https URL on the tenant's host. path_under_t is the part after /t/, e.g. 'finance/' or ''.
    """
    host = normalize_tenant_workspace_host(domain)
    if not host:
        return ""
    tail = (path_under_t or "").strip().lstrip("/")
    if tail:
        if not tail.endswith("/"):
            tail += "/"
        return f"https://{host}/t/{tail}"
    return f"https://{host}/t/"


def resolve_tenant_workspace_open_url(
    tenant: Tenant,
    *,
    enabled_tenant_modules: list[TenantModule] | None = None,
) -> dict[str, Any]:
    """
    Resolve the public "Open tenant workspace" destination for Platform Console.

    Uses short paths on the tenant domain (https://<tenant-domain>/t/...) so the request hits
    tenant routes instead of the marketing site at /.

    Returns:
        url: absolute https URL or None
        can_open: whether the action should be enabled
        disabled_reason: short message for tooltip / inline help
        warning: admin-facing issue (e.g. domain misconfiguration)
    """
    from tenants.models import TenantModule

    warning: str | None = None
    host = normalize_tenant_workspace_host(tenant.domain)
    if not host:
        warning = (
            "Workspace domain is not configured correctly. Set a valid hostname on the tenant "
            "(no protocol or path)."
        )
        return {
            "url": None,
            "can_open": False,
            "disabled_reason": warning,
            "warning": warning,
        }

    if enabled_tenant_modules is None:
        enabled_tenant_modules = list(
            TenantModule.objects.filter(
                tenant=tenant,
                is_enabled=True,
                module__is_active=True,
            ).select_related("module")
        )

    if not enabled_tenant_modules:
        msg = "No active modules assigned to this tenant yet."
        return {
            "url": None,
            "can_open": False,
            "disabled_reason": msg,
            "warning": None,
        }

    ok, sub_msg = tenant_subscription_allows_workspace(tenant)
    if not ok:
        return {
            "url": None,
            "can_open": False,
            "disabled_reason": sub_msg,
            "warning": None,
        }

    tenant_app_modules = [tm for tm in enabled_tenant_modules if not is_platform_module(tm.module)]

    if len(tenant_app_modules) == 1:
        code = tenant_app_modules[0].module.code
        rel = tenant_module_home_relpath(code)
        path_under = rel if rel else ""
        url = build_tenant_workspace_public_url(tenant.domain, path_under)
        return {"url": url, "can_open": True, "disabled_reason": None, "warning": None}

    # Multiple tenant-app modules, or only platform modules: tenant home / module selector.
    url = build_tenant_workspace_public_url(tenant.domain, "")
    return {"url": url, "can_open": True, "disabled_reason": None, "warning": None}
