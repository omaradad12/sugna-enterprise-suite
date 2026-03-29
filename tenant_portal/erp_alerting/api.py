"""
Public API for views and services: structured alerts with severity, channels, deduplication, audit.
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from tenant_portal.erp_alerting.audit import record_critical_control_in_audit_log
from tenant_portal.erp_alerting.collector import ErpAlertCollector, ErpAlertItem
from tenant_portal.erp_alerting.constants import AlertChannel, AlertSeverity


def get_collector(request: HttpRequest) -> ErpAlertCollector:
    """Return the request collector, creating a detached one if middleware did not run (e.g. tests)."""
    c = getattr(request, "erp_alerts", None)
    if isinstance(c, ErpAlertCollector):
        return c
    c = ErpAlertCollector()
    setattr(request, "erp_alerts", c)
    return c


def alert_critical_control(
    request: HttpRequest,
    code: str,
    message: str,
    *,
    field_name: str = "",
    tenant_db: str | None = None,
    audit_log: bool = True,
    audit_extra: dict[str, Any] | None = None,
    action_label: str = "",
    action_url: str = "",
) -> None:
    """
    Real control failure — user should not complete the blocked action until resolved.
    Field-level: pass field_name (banner + inline). Page-level: omit field_name.
    """
    col = get_collector(request)
    channel = AlertChannel.FIELD.value if field_name else AlertChannel.PAGE_BANNER.value
    col.add(
        severity=AlertSeverity.CRITICAL.value,
        code=code,
        message=message,
        channel=channel,
        field_name=field_name,
        action_label=action_label,
        action_url=action_url,
    )
    if audit_log and tenant_db:
        record_critical_control_in_audit_log(
            using=tenant_db,
            request=request,
            code=code,
            message=message,
            extra=audit_extra,
        )


def alert_warning_risk(
    request: HttpRequest,
    code: str,
    message: str,
    *,
    field_name: str = "",
    action_label: str = "",
    action_url: str = "",
) -> None:
    """Risk or policy reminder — allow save/post but surface prominently."""
    col = get_collector(request)
    channel = AlertChannel.FIELD.value if field_name else AlertChannel.PAGE_BANNER.value
    col.add(
        severity=AlertSeverity.WARNING.value,
        code=code,
        message=message,
        channel=channel,
        field_name=field_name,
        action_label=action_label,
        action_url=action_url,
    )


def alert_info_toast(request: HttpRequest, message: str, *, code: str = "info") -> None:
    """Success or neutral workflow confirmation (toast)."""
    get_collector(request).add(
        severity=AlertSeverity.INFO.value,
        code=code,
        message=message,
        channel=AlertChannel.TOAST.value,
    )


def queue_workflow_notification(
    request: HttpRequest,
    title: str,
    message: str,
    *,
    code: str = "workflow",
    severity: str = AlertSeverity.INFO.value,
    action_url: str = "",
    action_label: str = "",
) -> None:
    """
    Items intended for the notification bell / center (reminders, approvals, hand-offs).
    Shown alongside computed smart_alerts via context processor.
    """
    col = get_collector(request)
    text = f"{title}: {message}" if title else message
    col.add(
        severity=severity,
        code=code,
        message=text,
        channel=AlertChannel.NOTIFICATION_CENTER.value,
        action_url=action_url,
        action_label=action_label or title,
    )


def collector_to_template_context(col: ErpAlertCollector) -> dict[str, Any]:
    """Serialize collector for templates."""

    def _item_dict(x: ErpAlertItem) -> dict[str, Any]:
        return {
            "severity": x.severity,
            "code": x.code,
            "message": x.message,
            "field_name": x.field_name,
            "action_label": x.action_label,
            "action_url": x.action_url,
            "roles_hint": x.roles_hint,
        }

    fields: dict[str, list[dict[str, Any]]] = {}
    for k, items in col.field_issues.items():
        fields[k] = [_item_dict(i) for i in items]

    return {
        "erp_page_banners": [_item_dict(i) for i in col.page_banners],
        "erp_field_issues": fields,
        "erp_toasts": [_item_dict(i) for i in col.toasts],
        "erp_workflow_notifications": [_item_dict(i) for i in col.workflow_notifications],
        "erp_blocks_action": col.blocks_action,
    }
