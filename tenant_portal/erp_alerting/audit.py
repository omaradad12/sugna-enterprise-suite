"""
Write critical control alerts to tenant financial audit log (AuditLog).
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest


def record_critical_control_in_audit_log(
    *,
    using: str,
    request: HttpRequest | None,
    code: str,
    message: str,
    extra: dict[str, Any] | None = None,
) -> None:
    """
    Persist a critical control outcome for compliance review.
    Uses model_name=erp.control_alert so it appears in audit queries filtering by model.
    """
    try:
        from tenant_finance.models import AuditLog
    except Exception:
        return

    user_id = None
    username = ""
    if request is not None:
        u = getattr(request, "tenant_user", None)
        if u is not None:
            user_id = getattr(u, "pk", None) or getattr(u, "id", None)
            username = (getattr(u, "full_name", None) or getattr(u, "email", None) or "")[:150]

    payload = {"alert_code": code, "detail": (extra or {})}
    try:
        AuditLog.objects.using(using).create(
            model_name="erp.control_alert",
            object_id=0,
            action=AuditLog.Action.CREATE,
            user_id=user_id,
            username=username,
            old_data=None,
            new_data=payload,
            summary=(message or "")[:255],
        )
    except Exception:
        pass
