"""
Context processors for tenant portal templates.
Adds org_settings, tenant_display_name, and smart_alerts for the notification bell and dashboards.
"""


def org_settings(request):
    """Add org_settings (tenant's Organization Settings) and tenant_display_name when in a tenant context."""
    tenant = getattr(request, "tenant", None)
    if not tenant or not getattr(tenant, "db_name", None):
        return {
            "org_settings": None,
            "tenant_display_name": None,
            "can_access_adjusting_journals": False,
        }
    try:
        from tenants.db import ensure_tenant_db_configured, tenant_db_alias
        from tenant_finance.models import OrganizationSettings
        from rbac.models import user_has_permission

        ensure_tenant_db_configured(tenant)
        alias = tenant_db_alias(tenant)
        settings = OrganizationSettings.objects.using(alias).first()
        display_name = None
        if settings and getattr(settings, "organization_name", None):
            n = (settings.organization_name or "").strip()
            if n:
                display_name = n
        user = getattr(request, "tenant_user", None)
        can_adjusting = False
        if user:
            cached = getattr(request, "rbac_permission_codes", None)
            if isinstance(cached, set) and ("*" in cached or "finance:journals.adjusting" in cached):
                can_adjusting = True
            else:
                can_adjusting = user_has_permission(user, "finance:journals.adjusting", using=alias)
        return {
            "org_settings": settings,
            "tenant_display_name": display_name,
            "can_access_adjusting_journals": can_adjusting,
        }
    except Exception:
        return {
            "org_settings": None,
            "tenant_display_name": None,
            "can_access_adjusting_journals": False,
        }


def smart_alerts(request):
    """Add smart_alerts and smart_alerts_count for notification bell and dashboards (when in tenant context)."""
    tenant_db = getattr(request, "tenant_db", None)
    if not tenant_db or not getattr(request, "tenant", None):
        return {"smart_alerts": [], "smart_alerts_count": 0}
    try:
        from tenant_portal.smart_alerts import get_smart_alerts
        alerts = get_smart_alerts(tenant_db)
        return {"smart_alerts": alerts, "smart_alerts_count": len(alerts)}
    except Exception:
        return {"smart_alerts": [], "smart_alerts_count": 0}
