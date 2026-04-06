"""
Canonical module catalog for the control plane (seed_platform / sync_modules).

Each entry: (code, name, **optional defaults for Module fields)
"""
from __future__ import annotations

from typing import Any

# (code, name, extra_field_dict)
PLATFORM_MODULE_DEFINITIONS: list[tuple[str, str, dict[str, Any]]] = [
    ("finance_grants", "Financial & Grant Management", {"category": "core", "sort_order": 10}),
    ("hospital", "Hospital Management System", {"category": "core", "sort_order": 15}),
    ("integrations", "Integrations & API", {"category": "platform", "sort_order": 20}),
    ("audit_risk", "Audit & Risk Management", {"category": "governance", "sort_order": 30}),
    ("help_center", "Help Center", {"category": "platform", "sort_order": 40}),
    ("diagnostics", "System Diagnostics", {"category": "platform", "sort_order": 50}),
]

# (code, name, description, sort_order)
DEFAULT_SUBSCRIPTION_PLANS: list[tuple[str, str, str, int]] = [
    ("trial", "Trial", "Time-limited evaluation access.", 10),
    ("standard", "Standard", "Production NGO tier with core modules.", 20),
    ("enterprise", "Enterprise", "Extended limits and support.", 30),
]
