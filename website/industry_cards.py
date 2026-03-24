"""Marketing copy for the /industries/ page (sector cards)."""

from __future__ import annotations

from typing import TypedDict


class IndustryCard(TypedDict):
    title: str
    icon: str
    description: str


INDUSTRY_CARDS: list[IndustryCard] = [
    {
        "title": "NGOs",
        "icon": "mi-globe",
        "description": (
            "Organizations managing multiple donors, restricted funding, and field programs across regions "
            "with strong accountability requirements."
        ),
    },
    {
        "title": "Humanitarian organizations",
        "icon": "mi-zap",
        "description": (
            "Emergency and relief organizations requiring rapid deployment, procurement control, "
            "and financial transparency during crisis response."
        ),
    },
    {
        "title": "Hospitals & clinics",
        "icon": "mi-hospital",
        "description": (
            "Healthcare providers managing patient services, pharmacy inventory, billing, and financial operations "
            "within one integrated system."
        ),
    },
    {
        "title": "Foundations",
        "icon": "mi-coins",
        "description": (
            "Grant-making organizations managing funding allocations, grantee reporting, compliance, "
            "and portfolio-level performance tracking."
        ),
    },
    {
        "title": "Development agencies",
        "icon": "mi-landmark",
        "description": (
            "Bilateral and multilateral organizations managing complex programs requiring strong internal controls "
            "and transparent reporting of public funds."
        ),
    },
    {
        "title": "Government projects",
        "icon": "mi-shield",
        "description": (
            "Public sector programs requiring budget control, audit readiness, and transparent financial management."
        ),
    },
    {
        "title": "Research institutions",
        "icon": "mi-graduation",
        "description": (
            "Universities and research entities managing grants, funding allocations, and compliance reporting."
        ),
    },
    {
        "title": "International organizations",
        "icon": "mi-building",
        "description": (
            "Multi-country entities managing consolidated reporting across regional offices and programs."
        ),
    },
    {
        "title": "Corporate social responsibility (CSR) programs",
        "icon": "mi-sparkles",
        "description": (
            "Companies managing donor-funded initiatives and impact reporting."
        ),
    },
]
