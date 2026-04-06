"""
Config-driven Platform Admin navigation.

Sections and items are data; resolve URLs and active state at render time.
Extend PLATFORM_MENU_SECTIONS to add routes — use url_name for named routes,
href for Django admin or external paths, and active_prefix for active highlighting.
"""

from __future__ import annotations

from typing import Any

from django.urls import NoReverseMatch, reverse


def resolve_item_href(item: dict[str, Any]) -> str:
    if item.get("href"):
        return item["href"]
    ns = item.get("namespace", "platform_dashboard")
    name = item.get("url_name")
    if not name:
        return "#"
    kw = item.get("kwargs") or {}
    try:
        if kw:
            return reverse(f"{ns}:{name}", kwargs=kw)
        return reverse(f"{ns}:{name}")
    except NoReverseMatch:
        return "#"


def item_is_active(request, item: dict[str, Any]) -> bool:
    path = getattr(request, "path", "") or ""
    if item.get("active_prefix"):
        return path.startswith(item["active_prefix"])
    rm = getattr(request, "resolver_match", None)
    if not rm or not item.get("url_name"):
        return False
    names = [item["url_name"]] + list(item.get("alt_url_names", []))
    if rm.url_name not in names:
        return False
    item_kw = item.get("kwargs") or {}
    if "slug" in item_kw:
        return getattr(rm, "kwargs", {}).get("slug") == item_kw["slug"]
    return True


def build_sidebar_menu(request) -> list[dict[str, Any]]:
    """Return menu sections with resolved href and active flags for the current request."""
    user = getattr(request, "user", None)
    is_staff = bool(user and getattr(user, "is_staff", False))
    is_superuser = bool(user and getattr(user, "is_superuser", False))

    def allow(item: dict[str, Any]) -> bool:
        perm = item.get("permission_required")
        if perm == "superuser":
            return is_superuser
        if perm == "staff":
            return is_staff
        return is_staff

    out: list[dict[str, Any]] = []
    for sec in PLATFORM_MENU_SECTIONS:
        items_out = []
        for it in sec.get("items", []):
            if not allow(it):
                continue
            href = resolve_item_href(it)
            active = item_is_active(request, {**it, "href": href})
            items_out.append({**it, "href": href, "active": active})
        if items_out:
            out.append(
                {
                    **sec,
                    "items": items_out,
                    "default_open": bool(sec.get("default_open", True)),
                }
            )
    return out


# ---------------------------------------------------------------------------
# Menu definition — order matches product IA; href used where no named route exists
# ---------------------------------------------------------------------------

PLATFORM_MENU_SECTIONS: list[dict[str, Any]] = [
    {
        "id": "platform",
        "label": "Platform",
        "icon": "home",
        "default_open": True,
        "items": [
            {
                "label": "Dashboard",
                "icon": "layout",
                "url_name": "dashboard",
                "namespace": "platform_dashboard",
                "alt_url_names": ["dashboard_home"],
            },
        ],
    },
    {
        "id": "tenants",
        "label": "Tenants",
        "icon": "building",
        "default_open": True,
        "items": [
            {"label": "Tenant Directory", "icon": "layers", "url_name": "tenant_list", "namespace": "platform_dashboard"},
            {"label": "Tenant Users", "icon": "users", "url_name": "platform_users", "namespace": "platform_dashboard"},
            {"label": "Register Tenant", "icon": "user-plus", "url_name": "tenant_register", "namespace": "platform_dashboard"},
            {"label": "Tenant Domains", "icon": "globe", "href": "/admin/tenants/tenantdomain/", "active_prefix": "/admin/tenants/tenantdomain"},
            {"label": "Tenant Usage", "icon": "bar-chart-2", "url_name": "coming_soon", "namespace": "platform_dashboard", "kwargs": {"slug": "tenant-usage"}},
        ],
    },
    {
        "id": "tenant_operations",
        "label": "Tenant operations",
        "icon": "settings",
        "default_open": False,
        "items": [
            {"label": "Provisioning logs", "icon": "file-text", "url_name": "coming_soon", "namespace": "platform_dashboard", "kwargs": {"slug": "provisioning-logs"}},
            {"label": "Suspended tenants", "icon": "slash", "url_name": "coming_soon", "namespace": "platform_dashboard", "kwargs": {"slug": "suspended-tenants"}},
            {"label": "Tenant backups", "icon": "hard-drive", "url_name": "coming_soon", "namespace": "platform_dashboard", "kwargs": {"slug": "tenant-backups"}},
        ],
    },
    {
        "id": "subscriptions",
        "label": "Subscriptions",
        "icon": "credit-card",
        "default_open": True,
        "items": [
            {
                "label": "Plans",
                "icon": "package",
                "url_name": "plans_list",
                "namespace": "platform_dashboard",
                "active_prefix": "/platform/plans",
            },
            {
                "label": "Tenant subscriptions",
                "icon": "repeat",
                "url_name": "tenant_subscriptions",
                "namespace": "platform_dashboard",
                "active_prefix": "/platform/subscriptions",
            },
            {
                "label": "Trials",
                "icon": "clock",
                "url_name": "trials",
                "namespace": "platform_dashboard",
                "active_prefix": "/platform/trials",
            },
        ],
    },
    {
        "id": "module_management",
        "label": "Module management",
        "icon": "grid",
        "default_open": True,
        "items": [
            {"label": "Modules", "icon": "grid", "url_name": "module_list", "namespace": "platform_dashboard"},
            {"label": "Module categories", "icon": "tag", "url_name": "coming_soon", "namespace": "platform_dashboard", "kwargs": {"slug": "module-categories"}},
            {"label": "Module versions", "icon": "git-branch", "url_name": "coming_soon", "namespace": "platform_dashboard", "kwargs": {"slug": "module-versions"}},
            {"label": "Module marketplace", "icon": "shopping-bag", "url_name": "coming_soon", "namespace": "platform_dashboard", "kwargs": {"slug": "module-marketplace"}},
        ],
    },
    {
        "id": "billing",
        "label": "Billing",
        "icon": "dollar-sign",
        "default_open": False,
        "items": [
            {"label": "Invoices", "icon": "file-text", "url_name": "coming_soon", "namespace": "platform_dashboard", "kwargs": {"slug": "invoices"}},
            {"label": "Payments", "icon": "credit-card", "url_name": "coming_soon", "namespace": "platform_dashboard", "kwargs": {"slug": "payments"}},
            {"label": "Revenue reports", "icon": "trending-up", "url_name": "coming_soon", "namespace": "platform_dashboard", "kwargs": {"slug": "revenue-reports"}},
        ],
    },
    {
        "id": "support",
        "label": "Support",
        "icon": "help-circle",
        "default_open": False,
        "items": [
            {"label": "Tickets", "icon": "message-circle", "url_name": "coming_soon", "namespace": "platform_dashboard", "kwargs": {"slug": "tickets"}},
            {"label": "Complaints", "icon": "alert-circle", "url_name": "coming_soon", "namespace": "platform_dashboard", "kwargs": {"slug": "complaints"}},
            {"label": "Feature requests", "icon": "zap", "url_name": "coming_soon", "namespace": "platform_dashboard", "kwargs": {"slug": "feature-requests"}},
        ],
    },
    {
        "id": "communication",
        "label": "Communication",
        "icon": "message-square",
        "default_open": True,
        "items": [
            {"label": "Announcements", "icon": "volume-2", "url_name": "announcement_list", "namespace": "platform_dashboard"},
            {"label": "Notification templates", "icon": "bell", "url_name": "coming_soon", "namespace": "platform_dashboard", "kwargs": {"slug": "notification-templates"}},
            {"label": "Email templates", "icon": "mail", "url_name": "email_template_list", "namespace": "platform_dashboard", "active_prefix": "/platform/email-templates"},
        ],
    },
    {
        "id": "monitoring",
        "label": "Monitoring",
        "icon": "activity",
        "default_open": False,
        "items": [
            {"label": "System health", "icon": "heart", "url_name": "diagnostics", "namespace": "platform_dashboard"},
            {"label": "Logs", "icon": "list", "url_name": "coming_soon", "namespace": "platform_dashboard", "kwargs": {"slug": "logs"}},
            {"label": "Background jobs", "icon": "refresh-cw", "url_name": "coming_soon", "namespace": "platform_dashboard", "kwargs": {"slug": "background-jobs"}},
            {"label": "Backup monitor", "icon": "database", "url_name": "coming_soon", "namespace": "platform_dashboard", "kwargs": {"slug": "backup-monitor"}},
        ],
    },
    {
        "id": "security",
        "label": "Security",
        "icon": "shield",
        "default_open": False,
        "items": [
            {"label": "Platform users", "icon": "users", "href": "/admin/auth/user/", "active_prefix": "/admin/auth/user"},
            {"label": "Roles & permissions", "icon": "lock", "href": "/admin/auth/group/", "active_prefix": "/admin/auth/group"},
            {"label": "Audit log", "icon": "eye", "href": "/admin/admin/logentry/", "active_prefix": "/admin/admin/logentry"},
            {"label": "Authentication settings", "icon": "key", "url_name": "coming_soon", "namespace": "platform_dashboard", "kwargs": {"slug": "auth-settings"}},
        ],
    },
    {
        "id": "integrations",
        "label": "Integrations",
        "icon": "link",
        "default_open": False,
        "items": [
            {"label": "Integrations hub", "icon": "link", "url_name": "integrations_hub", "namespace": "platform_dashboard"},
            {"label": "Payment gateways", "icon": "dollar-sign", "url_name": "coming_soon", "namespace": "platform_dashboard", "kwargs": {"slug": "payment-gateways"}},
            {"label": "Email providers", "icon": "mail", "url_name": "coming_soon", "namespace": "platform_dashboard", "kwargs": {"slug": "email-providers"}},
            {"label": "SMS providers", "icon": "smartphone", "url_name": "coming_soon", "namespace": "platform_dashboard", "kwargs": {"slug": "sms-providers"}},
            {"label": "API keys", "icon": "key", "url_name": "coming_soon", "namespace": "platform_dashboard", "kwargs": {"slug": "api-keys"}},
            {"label": "Webhooks", "icon": "share-2", "url_name": "coming_soon", "namespace": "platform_dashboard", "kwargs": {"slug": "webhooks"}},
        ],
    },
    {
        "id": "settings",
        "label": "Settings",
        "icon": "sliders",
        "default_open": False,
        "items": [
            {"label": "Platform settings", "icon": "settings", "url_name": "coming_soon", "namespace": "platform_dashboard", "kwargs": {"slug": "platform-settings"}},
            {"label": "Email templates", "icon": "mail", "url_name": "coming_soon", "namespace": "platform_dashboard", "kwargs": {"slug": "email-templates"}},
            {"label": "Notifications", "icon": "bell", "url_name": "coming_soon", "namespace": "platform_dashboard", "kwargs": {"slug": "notifications"}},
            {"label": "Storage settings", "icon": "hard-drive", "url_name": "coming_soon", "namespace": "platform_dashboard", "kwargs": {"slug": "storage-settings"}},
            {"label": "Platform branding", "icon": "image", "url_name": "coming_soon", "namespace": "platform_dashboard", "kwargs": {"slug": "platform-branding"}},
        ],
    },
]
