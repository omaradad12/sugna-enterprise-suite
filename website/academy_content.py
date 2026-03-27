"""Structured marketing content for Sugna Academy (courses, paths, certifications)."""

from __future__ import annotations

# Training category labels — umbrella for all Sugna modules and professional skills.
TRAINING_CATEGORIES: list[dict[str, str]] = [
    {"slug": "sugna-software", "title": "Sugna Software Training", "summary": "Core navigation, security, workflows, and tenant administration across the suite.", "icon": "mi-grid"},
    {"slug": "financial-grant", "title": "Financial & Grant Management", "summary": "Fund accounting, grants, budgets, multi-currency, and donor reporting.", "icon": "mi-coins"},
    {"slug": "hr", "title": "Human Resource Management", "summary": "People records, payroll alignment, approvals, and role-based HR processes.", "icon": "mi-users"},
    {"slug": "procurement", "title": "Procurement & Logistics", "summary": "Requisitions, purchasing, inventory, and traceability from need to delivery.", "icon": "mi-package"},
    {"slug": "fleet", "title": "Fleet Management", "summary": "Vehicles, fuel, maintenance, and cost allocation across programs.", "icon": "mi-truck"},
    {"slug": "ai-auditor", "title": "AI Auditor", "summary": "Intelligent review signals, exception surfacing, and audit-ready documentation.", "icon": "mi-sparkles"},
    {"slug": "hospital", "title": "Hospital Management", "summary": "Clinical and operational workflows for regulated healthcare environments.", "icon": "mi-hospital"},
    {"slug": "corporate", "title": "Sugna Corporate Management", "summary": "Governance, policy, and executive oversight aligned to your operating model.", "icon": "mi-building"},
    {"slug": "ngo-skills", "title": "NGO Professional Skills", "summary": "Program finance, donor relations, and field operations best practices.", "icon": "mi-target"},
    {"slug": "compliance", "title": "Compliance & Risk", "summary": "Internal control, segregation of duties, and regulatory readiness.", "icon": "mi-shield"},
    {"slug": "ai-digital", "title": "AI & Digital Skills", "summary": "Responsible use of AI, data literacy, and secure digital collaboration.", "icon": "mi-zap"},
]

# Sample catalog — suitable for marketing; replace with LMS links when available.
ACADEMY_COURSES: list[dict[str, str]] = [
    {
        "slug": "suite-fundamentals",
        "title": "Sugna Suite Fundamentals",
        "description": "Orientation to the workspace, navigation, approvals, and security practices for new users.",
        "category": "Sugna Software Training",
        "category_slug": "sugna-software",
        "level": "Beginner",
        "duration": "3 h",
    },
    {
        "slug": "grant-budget-cycle",
        "title": "Grant Budgets & Burn Rates",
        "description": "Budget structures, dimensions, grant periods, and monitoring spend against donor rules.",
        "category": "Financial & Grant Management",
        "category_slug": "financial-grant",
        "level": "Intermediate",
        "duration": "4 h",
    },
    {
        "slug": "period-close-ngo",
        "title": "Period Close for NGO Finance",
        "description": "Month-end routines, reconciliations, and donor-ready close packs in Sugna.",
        "category": "Financial & Grant Management",
        "category_slug": "financial-grant",
        "level": "Advanced",
        "duration": "5 h",
    },
    {
        "slug": "hr-lifecycle",
        "title": "HR Records & Approvals",
        "description": "Employee lifecycle, position control, and segregation of duties in HR workflows.",
        "category": "Human Resource Management",
        "category_slug": "hr",
        "level": "Beginner",
        "duration": "3 h",
    },
    {
        "slug": "procure-to-pay",
        "title": "Procure-to-Pay in Depth",
        "description": "Requisitions, purchase orders, goods receipt, and three-way match patterns.",
        "category": "Procurement & Logistics",
        "category_slug": "procurement",
        "level": "Intermediate",
        "duration": "4 h",
    },
    {
        "slug": "fleet-cost-allocation",
        "title": "Fleet Cost Allocation",
        "description": "Vehicle usage, fuel, maintenance charging, and program-level allocation.",
        "category": "Fleet Management",
        "category_slug": "fleet",
        "level": "Intermediate",
        "duration": "3 h",
    },
    {
        "slug": "ai-auditor-review",
        "title": "AI Auditor for Review Teams",
        "description": "Configuring review rules, interpreting signals, and documenting responses.",
        "category": "AI Auditor",
        "category_slug": "ai-auditor",
        "level": "Intermediate",
        "duration": "3 h",
    },
    {
        "slug": "hospital-billing-basics",
        "title": "Hospital Billing & Handoffs",
        "description": "Front desk through billing with accuracy and audit trails for healthcare settings.",
        "category": "Hospital Management",
        "category_slug": "hospital",
        "level": "Beginner",
        "duration": "4 h",
    },
    {
        "slug": "governance-dashboards",
        "title": "Corporate Governance Dashboards",
        "description": "Executive KPIs, policy attestations, and oversight views for leadership.",
        "category": "Sugna Corporate Management",
        "category_slug": "corporate",
        "level": "Advanced",
        "duration": "3 h",
    },
    {
        "slug": "donor-compliance",
        "title": "Donor Compliance Essentials",
        "description": "Eligibility, allowability, and documentation patterns NGOs rely on for assurance.",
        "category": "NGO Professional Skills",
        "category_slug": "ngo-skills",
        "level": "Intermediate",
        "duration": "4 h",
    },
    {
        "slug": "risk-control-matrix",
        "title": "Risk & Control Mapping",
        "description": "Linking processes to risks, controls, and evidence for internal and external review.",
        "category": "Compliance & Risk",
        "category_slug": "compliance",
        "level": "Advanced",
        "duration": "4 h",
    },
    {
        "slug": "ai-digital-literacy",
        "title": "AI & Data Literacy for Teams",
        "description": "Responsible AI use, data handling, and secure collaboration in regulated contexts.",
        "category": "AI & Digital Skills",
        "category_slug": "ai-digital",
        "level": "Beginner",
        "duration": "2 h",
    },
]

LEARNING_PATHS: list[dict[str, str | list[str]]] = [
    {
        "slug": "finance-officer",
        "title": "Finance Officer Path",
        "summary": "Core journals, grants, dimensions, and month-end tasks for operational finance roles.",
        "courses": ["Grant Budgets & Burn Rates", "Period Close for NGO Finance", "Donor Compliance Essentials"],
        "duration": "approx. 13 h",
        "level": "Beginner → Intermediate",
    },
    {
        "slug": "finance-manager",
        "title": "Finance Manager Path",
        "summary": "Leadership of close, donor reporting, controls, and team coordination across sites.",
        "courses": ["Period Close for NGO Finance", "Risk & Control Mapping", "Corporate Governance Dashboards"],
        "duration": "approx. 12 h",
        "level": "Intermediate → Advanced",
    },
    {
        "slug": "hr-officer",
        "title": "HR Officer Path",
        "summary": "HR master data, approvals, and policy-aligned people processes in Sugna.",
        "courses": ["Sugna Suite Fundamentals", "HR Records & Approvals"],
        "duration": "approx. 6 h",
        "level": "Beginner",
    },
    {
        "slug": "procurement-officer",
        "title": "Procurement Officer Path",
        "summary": "End-to-end procurement discipline from requisition through inventory and audit trail.",
        "courses": ["Sugna Suite Fundamentals", "Procure-to-Pay in Depth"],
        "duration": "approx. 7 h",
        "level": "Beginner → Intermediate",
    },
    {
        "slug": "system-administrator",
        "title": "System Administrator Path",
        "summary": "Tenant configuration, users, roles, integrations, and safe change management.",
        "courses": ["Sugna Suite Fundamentals", "AI Auditor for Review Teams", "Risk & Control Mapping"],
        "duration": "approx. 10 h",
        "level": "Intermediate → Advanced",
    },
]

CERTIFICATIONS: list[dict[str, str]] = [
    {
        "slug": "cngofo",
        "title": "Certified NGO Finance Officer",
        "description": "Validates competency in fund accounting, grant stewardship, and period close within Sugna.",
        "audience": "Finance officers and assistants in NGO and donor-funded contexts",
    },
    {
        "slug": "cgm",
        "title": "Certified Grant Manager",
        "description": "Covers grant design, monitoring, compliance checkpoints, and reporting across programs.",
        "audience": "Program finance, grant managers, and MEAL leads",
    },
    {
        "slug": "cpo",
        "title": "Certified Procurement Officer",
        "description": "Demonstrates mastery of ethical procurement, approvals, and logistics traceability.",
        "audience": "Procurement and supply chain staff",
    },
    {
        "slug": "cco",
        "title": "Certified Compliance Officer",
        "description": "Maps risks, controls, and evidence workflows for audits and donor assurance.",
        "audience": "Compliance, risk, and internal audit roles",
    },
]

TUTORIALS: list[dict[str, str]] = [
    {
        "slug": "first-login",
        "title": "First login & security",
        "description": "Password policy, MFA where enabled, and session expectations for regulated tenants.",
        "format": "Video",
        "duration": "12 min",
    },
    {
        "slug": "approval-inbox",
        "title": "Working the approval inbox",
        "description": "Routing, delegations, and audit trail for multi-step approvals.",
        "format": "Video",
        "duration": "18 min",
    },
    {
        "slug": "grant-reports",
        "title": "Grant reporting exports",
        "description": "Standard donor views, dimensions, and reconciliation hooks before submission.",
        "format": "Guide",
        "duration": "10 min read",
    },
    {
        "slug": "inventory-adjustments",
        "title": "Inventory adjustments & recounts",
        "description": "Controlled adjustments with segregation of duties for warehouse teams.",
        "format": "Video",
        "duration": "15 min",
    },
]

WEBINAR_TRACKS: list[dict[str, str]] = [
    {
        "title": "Release readiness",
        "description": "What changed, how it affects journals and approvals, and how to validate in sandbox before go-live.",
    },
    {
        "title": "Sector scenarios",
        "description": "NGO grant cycles, hospital revenue alignment, fleet and field costs—walkthroughs with realistic data patterns.",
    },
    {
        "title": "Office hours",
        "description": "Open Q&A for administrators configuring users, dimensions, and integrations ahead of period close.",
    },
]
