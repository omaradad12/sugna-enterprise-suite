"""Customer Portal Templates marketing page — categories and copy."""

from __future__ import annotations

from typing import TypedDict


class TemplateCategory(TypedDict):
    slug: str
    title: str
    icon: str
    description: str


TPL_LEAD = (
    "Professional template packs for financial management, grant tracking, HR administration, "
    "procurement workflows, and compliance reporting."
)

TPL_STANDARDS = (
    "Templates are designed according to NGO and humanitarian standards and are compatible with "
    "Sugna Enterprise Suite modules."
)

TPL_ACCOUNT_NOTE = (
    "Entitlements are purchased and assigned per tenant; catalog updates and publisher uploads are "
    "coordinated through your Sugna account team (not via this public preview). Full self-service "
    "for this area opens in your signed-in customer portal when enabled for your tenant."
)

TPL_CATEGORIES: list[TemplateCategory] = [
    {
        "slug": "finance-grants",
        "title": "Financial & Grant Management",
        "icon": "mi-coins",
        "description": (
            "Standard chart of accounts, project budget structures, financial reports, and cost allocation templates."
        ),
    },
    {
        "slug": "projects-programs",
        "title": "Projects & Programs",
        "icon": "mi-target",
        "description": (
            "Project planning structures, activity templates, and logframe formats."
        ),
    },
    {
        "slug": "procurement",
        "title": "Procurement & Logistics",
        "icon": "mi-package",
        "description": (
            "Vendor forms, purchase workflows, and asset management templates."
        ),
    },
    {
        "slug": "hr",
        "title": "Human Resource Management",
        "icon": "mi-users",
        "description": (
            "Employee data structures, payroll templates, and HR forms."
        ),
    },
    {
        "slug": "compliance-audit",
        "title": "Compliance & Audit",
        "icon": "mi-clipboard-check",
        "description": (
            "Internal control checklists, audit preparation templates, and risk management tools."
        ),
    },
    {
        "slug": "hospital",
        "title": "Hospital Management",
        "icon": "mi-hospital",
        "description": (
            "Patient billing formats and clinical inventory templates."
        ),
    },
]
