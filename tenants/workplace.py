"""
Module workplace path helpers (Platform → tenant deep links).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tenants.models import Module

# Relative to /t/<tenant_slug>/
TENANT_MODULE_HOME_REL_PATH: dict[str, str] = {
    "finance_grants": "finance/",
    "hospital": "hospital/",
    "audit_risk": "audit-risk/",
    "integrations": "integrations/",
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
    return TENANT_MODULE_HOME_REL_PATH.get(module_code, "")
