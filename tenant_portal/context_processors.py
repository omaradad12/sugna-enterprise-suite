"""
Context processors for tenant portal templates.
Adds org_settings, tenant_display_name, smart_alerts, and structured ERP alerting context.
"""

from tenant_portal.erp_alerting.api import collector_to_template_context
from tenant_portal.erp_alerting.collector import ErpAlertCollector
from tenant_portal.erp_alerting.constants import PRIORITY_CRITICAL, PRIORITY_WARNING


def _bell_alert_count(alerts: list) -> int:
    """Notification bell badge: critical + warning only (not informational)."""
    actionable = {PRIORITY_CRITICAL, PRIORITY_WARNING, "critical", "warning"}
    n = 0
    for a in alerts:
        p = (a.get("priority") or "").strip().lower()
        if p in actionable:
            n += 1
    return n


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


def _visible_smart_alerts_for_user(alerts: list, tenant_user, tenant_db: str) -> list:
    """Hide project end-date alerts from users who are not PM (on project) or admin/finance manage."""
    if not tenant_user:
        return [a for a in alerts if not a.get("restrict_to_pm_admin")]
    from rbac.models import user_has_permission
    from tenant_grants.models import Project

    out = []
    for a in alerts:
        if not a.get("restrict_to_pm_admin"):
            out.append(a)
            continue
        if getattr(tenant_user, "is_tenant_admin", False):
            out.append(a)
            continue
        if user_has_permission(tenant_user, "module:finance.manage", using=tenant_db):
            out.append(a)
            continue
        pids = a.get("project_ids") or []
        if pids and Project.objects.using(tenant_db).filter(
            pk__in=pids, project_manager_id=tenant_user.pk
        ).exists():
            out.append(a)
            continue
    return out


def smart_alerts(request):
    """Add smart_alerts and smart_alerts_count for notification bell and dashboards (when in tenant context)."""
    tenant_db = getattr(request, "tenant_db", None)
    if not tenant_db or not getattr(request, "tenant", None):
        return {"smart_alerts": [], "smart_alerts_count": 0}
    try:
        from tenant_portal.smart_alerts import get_smart_alerts

        alerts = get_smart_alerts(tenant_db)
        tenant_user = getattr(request, "tenant_user", None)
        alerts = _visible_smart_alerts_for_user(alerts, tenant_user, tenant_db)
        request._smart_alerts_cached = alerts
        return {
            "smart_alerts": alerts,
            "smart_alerts_count": _bell_alert_count(alerts),
        }
    except Exception:
        return {"smart_alerts": [], "smart_alerts_count": 0}


def erp_alerting(request):
    """
    Structured alerts: page banners, field map, toasts, workflow queue; merged notification list for bell.
    """
    empty = {
        "erp_page_banners": [],
        "erp_field_issues": {},
        "erp_toasts": [],
        "erp_workflow_notifications": [],
        "erp_blocks_action": False,
        "notification_center_items": [],
        "notification_center_count": 0,
    }
    col = getattr(request, "erp_alerts", None)
    if not isinstance(col, ErpAlertCollector):
        tenant_db = getattr(request, "tenant_db", None)
        if not tenant_db or not getattr(request, "tenant", None):
            return empty
        try:
            from tenant_portal.smart_alerts import get_smart_alerts

            base = getattr(request, "_smart_alerts_cached", None)
            if base is None:
                base = get_smart_alerts(tenant_db)
                tenant_user = getattr(request, "tenant_user", None)
                base = _visible_smart_alerts_for_user(base, tenant_user, tenant_db)
            return {
                **empty,
                "notification_center_items": base,
                "notification_center_count": _bell_alert_count(base),
            }
        except Exception:
            return empty

    ctx = collector_to_template_context(col)
    tenant_db = getattr(request, "tenant_db", None)
    merged: list = []
    if tenant_db and getattr(request, "tenant", None):
        try:
            merged = getattr(request, "_smart_alerts_cached", None)
            if merged is None:
                from tenant_portal.smart_alerts import get_smart_alerts

                merged = get_smart_alerts(tenant_db)
                tenant_user = getattr(request, "tenant_user", None)
                merged = _visible_smart_alerts_for_user(merged, tenant_user, tenant_db)
        except Exception:
            merged = []
    for w in ctx.get("erp_workflow_notifications", []):
        sev = (w.get("severity") or "info").strip().lower()
        if sev not in {"critical", "warning", "info"}:
            sev = "info"
        merged.append(
            {
                "category": "workflow",
                "category_label": "Internal control",
                "priority": sev,
                "title": (w.get("code") or "Workflow").replace("_", " ").title(),
                "message": w.get("message", ""),
                "link_url": w.get("action_url") or "#",
                "link_label": w.get("action_label") or "Open",
            }
        )
    ctx["notification_center_items"] = merged
    ctx["notification_center_count"] = _bell_alert_count(merged)
    return ctx
