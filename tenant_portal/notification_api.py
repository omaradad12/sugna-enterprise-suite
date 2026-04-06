"""
JSON API for notification bell polling — keeps alerts in sync with source data without full page reload.
"""

from __future__ import annotations

from django.http import HttpRequest, JsonResponse

from tenant_portal.context_processors import _bell_alert_count, _visible_smart_alerts_for_user
from tenant_portal.smart_alerts import get_smart_alerts


def build_notification_poll_payload(request: HttpRequest) -> dict:
    """
    Same effective list as the notification bell (smart alerts + user visibility rules).
    Per-request ERP/workflow collector items are not included here (they are ephemeral to specific pages).
    """
    tenant_db = getattr(request, "tenant_db", None)
    if not tenant_db or not getattr(request, "tenant", None):
        return {"items": [], "bell_count": 0}
    try:
        items = get_smart_alerts(tenant_db, tenant=getattr(request, "tenant", None))
        tenant_user = getattr(request, "tenant_user", None)
        items = _visible_smart_alerts_for_user(items, tenant_user, tenant_db)
        return {"items": items, "bell_count": _bell_alert_count(items)}
    except Exception:
        return {"items": [], "bell_count": 0}


def api_notifications_poll_view(request: HttpRequest) -> JsonResponse:
    """GET: { items: [...], bell_count: int } for Alpine / fetch polling."""
    payload = build_notification_poll_payload(request)
    return JsonResponse(payload, safe=False)
