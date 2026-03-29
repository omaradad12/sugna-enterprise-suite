"""
Structured ERP alerting: severities, channels, and stable codes for deduplication and audit.

Critical — blocks posting/save only for real control failures (period closed, inactive GL,
missing approval, missing posting rule, budget beyond tolerance, invalid donor/project link,
duplicate reference, etc.).

Warning — non-blocking; highlight risks (project end approaching, high budget use, stale FX,
recommended attachment missing).

Info — confirmations and routine workflow updates.
"""

from __future__ import annotations

from enum import Enum


class AlertSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AlertChannel(str, Enum):
    """Where an alert should surface in the UI."""

    FIELD = "field"
    PAGE_BANNER = "page_banner"
    TOAST = "toast"
    NOTIFICATION_CENTER = "notification_center"


# Stable codes for deduplication and audit (extend as modules adopt the framework)
class ControlFailureCode(str, Enum):
    """Critical control failures — use with alert_critical_control only."""

    PERIOD_CLOSED = "period_closed"
    ACCOUNT_INACTIVE = "account_inactive"
    APPROVAL_REQUIRED = "approval_required"
    POSTING_RULE_MISSING = "posting_rule_missing"
    BUDGET_OVERRUN = "budget_overrun"
    DONOR_PROJECT_LINK_INVALID = "donor_project_link_invalid"
    DUPLICATE_REFERENCE = "duplicate_reference"
    EXCHANGE_RATE_STALE = "exchange_rate_stale"  # when policy treats as hard block
    OTHER_CONTROL = "other_control"


class RiskWarningCode(str, Enum):
    """Non-blocking warnings."""

    PROJECT_ENDING_SOON = "project_ending_soon"
    BUDGET_HIGH_UTILIZATION = "budget_high_utilization"
    EXCHANGE_RATE_OUTDATED = "exchange_rate_outdated"
    ATTACHMENT_RECOMMENDED = "attachment_recommended"
    OTHER_RISK = "other_risk"


# Backwards compatibility with smart_alerts / templates using string priorities
PRIORITY_CRITICAL = AlertSeverity.CRITICAL.value
PRIORITY_WARNING = AlertSeverity.WARNING.value
PRIORITY_INFO = AlertSeverity.INFO.value
