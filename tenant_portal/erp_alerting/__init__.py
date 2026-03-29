"""
Structured ERP alerts: Critical / Warning / Info with field, banner, toast, and notification-center channels.

Use ``tenant_portal.erp_alerting.api`` from views and services. Critical control failures can be
audited via ``record_critical_control_in_audit_log`` (called from ``alert_critical_control`` when
``tenant_db`` is passed).

Existing ``smart_alerts`` feeds the notification bell with computed KPI-style alerts; request-scoped
workflow items are merged in the ``erp_alerting`` context processor.
"""

from tenant_portal.erp_alerting.api import (
    alert_critical_control,
    alert_info_toast,
    alert_warning_risk,
    get_collector,
    queue_workflow_notification,
)
from tenant_portal.erp_alerting.constants import (
    AlertChannel,
    AlertSeverity,
    ControlFailureCode,
    PRIORITY_CRITICAL,
    PRIORITY_INFO,
    PRIORITY_WARNING,
    RiskWarningCode,
)

__all__ = [
    "AlertChannel",
    "AlertSeverity",
    "ControlFailureCode",
    "RiskWarningCode",
    "PRIORITY_CRITICAL",
    "PRIORITY_WARNING",
    "PRIORITY_INFO",
    "get_collector",
    "alert_critical_control",
    "alert_warning_risk",
    "alert_info_toast",
    "queue_workflow_notification",
]
