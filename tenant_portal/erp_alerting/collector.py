"""
Per-request collection of structured alerts (field, banner, toast, notification center).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from tenant_portal.erp_alerting.constants import AlertChannel, AlertSeverity


@dataclass
class ErpAlertItem:
    severity: str
    code: str
    message: str
    channel: str
    field_name: str = ""
    action_label: str = ""
    action_url: str = ""
    roles_hint: str = ""  # e.g. "finance_approver" for display filtering later


@dataclass
class ErpAlertCollector:
    """Attached to request by middleware; deduplicates by (severity, code, field, message)."""

    page_banners: list[ErpAlertItem] = field(default_factory=list)
    field_issues: dict[str, list[ErpAlertItem]] = field(default_factory=dict)
    toasts: list[ErpAlertItem] = field(default_factory=list)
    workflow_notifications: list[ErpAlertItem] = field(default_factory=list)
    blocks_action: bool = False
    _dedupe_keys: set[str] = field(default_factory=set)

    def _dedupe(self, severity: str, code: str, field_name: str, message: str) -> bool:
        raw = f"{severity}|{code}|{field_name}|{message}"
        key = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]
        if key in self._dedupe_keys:
            return False
        self._dedupe_keys.add(key)
        return True

    def add(
        self,
        *,
        severity: str,
        code: str,
        message: str,
        channel: str,
        field_name: str = "",
        action_label: str = "",
        action_url: str = "",
        roles_hint: str = "",
    ) -> None:
        if not message or not message.strip():
            return
        if not self._dedupe(severity, code, field_name, message.strip()):
            return
        item = ErpAlertItem(
            severity=severity,
            code=code,
            message=message.strip(),
            channel=channel,
            field_name=field_name,
            action_label=action_label or "",
            action_url=action_url or "",
            roles_hint=roles_hint or "",
        )
        if channel == AlertChannel.FIELD.value and field_name:
            self.field_issues.setdefault(field_name, []).append(item)
            if severity == AlertSeverity.CRITICAL.value:
                self.blocks_action = True
        elif channel == AlertChannel.PAGE_BANNER.value:
            self.page_banners.append(item)
            if severity == AlertSeverity.CRITICAL.value:
                self.blocks_action = True
        elif channel == AlertChannel.TOAST.value:
            self.toasts.append(item)
        elif channel == AlertChannel.NOTIFICATION_CENTER.value:
            self.workflow_notifications.append(item)
