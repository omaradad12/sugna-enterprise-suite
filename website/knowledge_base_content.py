"""Knowledge Base marketing page — categories, icons, and sample article links."""

from __future__ import annotations

from typing import TypedDict


class KBArticle(TypedDict):
    title: str
    href: str


class KBCategory(TypedDict):
    slug: str
    title: str
    icon: str
    description: str
    articles: list[KBArticle]


KB_LEAD = (
    "Find guides and documentation for configuring Sugna Enterprise Suite modules including Finance, Grants, "
    "HR, Procurement, AI Auditor, and system administration."
)

KB_CATEGORIES: list[KBCategory] = [
    {
        "slug": "finance-grants",
        "title": "Financial & Grant Management",
        "icon": "mi-coins",
        "description": "Set up chart of accounts, donor funds, budgets, and financial reports.",
        "articles": [
            {"title": "Chart of accounts and dimensions", "href": "#chart-of-accounts"},
            {"title": "Donor funds and grant reporting", "href": "#donor-funds"},
            {"title": "Budget setup and burn-rate tracking", "href": "#budgets"},
        ],
    },
    {
        "slug": "projects-programs",
        "title": "Projects & Programs",
        "icon": "mi-target",
        "description": "Manage projects, activities, and grant budgets.",
        "articles": [
            {"title": "Project structure and coding", "href": "#projects"},
            {"title": "Activities and workplans", "href": "#activities"},
            {"title": "Grant budgets vs actuals", "href": "#grant-budgets"},
        ],
    },
    {
        "slug": "procurement",
        "title": "Procurement & Logistics",
        "icon": "mi-package",
        "description": "Configure vendor management and purchasing workflows.",
        "articles": [
            {"title": "Vendor master and qualification", "href": "#vendors"},
            {"title": "Requisitions and approvals", "href": "#requisitions"},
            {"title": "Purchase orders and receiving", "href": "#purchase-orders"},
        ],
    },
    {
        "slug": "hr",
        "title": "Human Resource Management",
        "icon": "mi-users",
        "description": "Manage employees, contracts, and payroll preparation.",
        "articles": [
            {"title": "Employee records and org structure", "href": "#employees"},
            {"title": "Contracts and documents", "href": "#contracts"},
            {"title": "Leave, attendance, and payroll interfaces", "href": "#payroll"},
        ],
    },
    {
        "slug": "ai-auditor",
        "title": "AI Financial Auditor",
        "icon": "mi-sparkles",
        "description": "Automate compliance checks and financial risk detection.",
        "articles": [
            {"title": "Rules and threshold configuration", "href": "#ai-rules"},
            {"title": "Exception queues and review", "href": "#exceptions"},
            {"title": "Assurance reporting for audits", "href": "#assurance"},
        ],
    },
    {
        "slug": "administration",
        "title": "System Administration",
        "icon": "mi-settings",
        "description": "Manage users, tenants, modules, and configurations.",
        "articles": [
            {"title": "Users, roles, and security", "href": "#users-roles"},
            {"title": "Tenant and module entitlements", "href": "#modules"},
            {"title": "Environment configuration", "href": "#configuration"},
        ],
    },
]
