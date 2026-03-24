"""Marketing copy for /modules/ listing and /modules/<slug>/ detail pages."""

from __future__ import annotations

from typing import TypedDict


class FeatureGroup(TypedDict):
    heading: str
    items: list[str]


class ModulePage(TypedDict):
    slug: str
    index: int
    title: str
    tagline: str
    icon: str
    meta_description: str
    summary_bullets: list[str]
    feature_groups: list[FeatureGroup]


MODULE_PAGES_ORDERED: list[ModulePage] = [
    {
        "slug": "financial-grant-management",
        "index": 1,
        "title": "Financial & Grant Management",
        "tagline": "Fund accounting, donor accountability, and multi-entity reporting for NGOs and grant-funded programmes.",
        "icon": "mi-coins",
        "meta_description": (
            "Sugna Financial & Grant Management: fund accounting, donor and grant visibility, "
            "project budgets, compliance checkpoints, and multi-currency reporting."
        ),
        "summary_bullets": [
            "Fund accounting and chart of accounts for restricted and unrestricted funds",
            "Multi-entity, multi-currency accounting with controlled rates and translation",
            "Donor dimensions, grant visibility, and multi-donor / multi-grant reporting",
            "Grant budgets, burn rates, and compliance checkpoints against award terms",
            "Project budgets tied to programmes, locations, and funding sources",
            "Period close, journals, and audit-ready transaction trails",
            "Financial statements, management reporting, and donor narrative packs",
            "Segregation of duties and role-based access across HQ and field offices",
        ],
        "feature_groups": [
            {
                "heading": "Fund accounting & structure",
                "items": [
                    "Chart of accounts aligned to restricted and unrestricted funds",
                    "Dimensional coding for programs, projects, and locations",
                    "Period close, journals, and audit-ready transaction trails",
                    "Allocations and cost centres mapped to donor rules",
                ],
            },
            {
                "heading": "Donors, grants & compliance",
                "items": [
                    "Donor profiles, commitments, and multi-grant dashboards",
                    "Budget vs actual with burn-rate and milestone tracking",
                    "Compliance checkpoints and exception alerts for award terms",
                    "Linkage from procurement and HR costs to grant budgets",
                ],
            },
            {
                "heading": "Reporting & multi-currency",
                "items": [
                    "Financial statements and donor-specific reporting packs",
                    "Management dashboards for HQ and field leadership",
                    "Controlled exchange rates, revaluation, and translation",
                    "Export and consolidation hooks for external auditors",
                ],
            },
        ],
    },
    {
        "slug": "human-resource-management",
        "index": 2,
        "title": "Human Resource Management",
        "tagline": "Centralized people data, workforce processes, and labour visibility across entities and programmes.",
        "icon": "mi-users",
        "meta_description": (
            "Sugna HRM: employee records, org structure, contracts, attendance, leave, payroll interfaces, "
            "and performance workflows for distributed teams."
        ),
        "summary_bullets": [
            "Employee master, positions, and reporting lines across entities and projects",
            "Org structure for HQ, field offices, programmes, and cost centres",
            "Contracts, documents, and personnel records with governance hooks",
            "Leave, attendance, and policies aligned to operating rules",
            "Payroll preparation interfaces and statutory reporting integrations",
            "Performance management and review cycles",
            "HR analytics aligned to programme costing and grant labour",
        ],
        "feature_groups": [
            {
                "heading": "Core HR & organization",
                "items": [
                    "Employee master, positions, and reporting lines",
                    "Org units for HQ, field offices, and projects",
                    "Job history, qualifications, and compliance fields",
                    "Document storage hooks for contracts and HR files",
                ],
            },
            {
                "heading": "Time, leave & attendance",
                "items": [
                    "Leave types, entitlements, and approval workflows",
                    "Attendance capture and exceptions",
                    "Holiday calendars by location or entity",
                    "Integration points for biometric or third-party clocks",
                ],
            },
            {
                "heading": "Payroll & performance",
                "items": [
                    "Payroll preparation outputs and statutory reporting interfaces",
                    "Benefits and deductions configuration",
                    "Goal setting, reviews, and performance cycles",
                    "HR analytics aligned to finance and program costing",
                ],
            },
        ],
    },
    {
        "slug": "procurement-logistics",
        "index": 3,
        "title": "Procurement & Logistics",
        "tagline": "Source-to-pay and inventory control with approvals, audit trails, and grant-aware coding.",
        "icon": "mi-package",
        "meta_description": (
            "Sugna Procurement & Logistics: supplier management, requisitions, RFQ, POs, receiving, "
            "inventory, warehouses, and approvals aligned to policy."
        ),
        "summary_bullets": [
            "Supplier master, qualification, and performance tracking",
            "Procurement workflows from purchase request through approval",
            "RFQ, competitive sourcing, and award documentation",
            "Purchase orders, goods receipt, three-way match, and returns",
            "Approval matrices by threshold, project, and donor rules",
            "Inventory, stock movements, and multi-site warehouse visibility",
            "End-to-end traceability from requisition to payment for audits and donors",
        ],
        "feature_groups": [
            {
                "heading": "Sourcing & suppliers",
                "items": [
                    "Supplier registration, categories, and performance",
                    "Purchase requests with budget and grant checks",
                    "RFQ, quotations, and award documentation",
                    "Contract and framework agreement tracking",
                ],
            },
            {
                "heading": "Orders, receiving & inventory",
                "items": [
                    "Purchase orders with line-level project and grant coding",
                    "Goods receipt, three-way match, and returns",
                    "Stock levels, batches, and movements across sites",
                    "Reservation against projects and emergency pipelines",
                ],
            },
            {
                "heading": "Warehousing & logistics",
                "items": [
                    "Multi-warehouse and bin management",
                    "Transfers, dispatch, and in-transit visibility",
                    "Integration with fleet and field distribution",
                    "Audit trail from requisition to payment",
                ],
            },
        ],
    },
    {
        "slug": "fleet-management",
        "index": 4,
        "title": "Fleet Management",
        "tagline": "Field fleet operations, cost control, and programme-linked mobility across sites.",
        "icon": "mi-truck",
        "meta_description": (
            "Sugna Fleet Management: vehicle registry, maintenance, fuel and mileage, drivers, "
            "and integration with logistics and approvals."
        ),
        "summary_bullets": [
            "Vehicle registry, assignments, and utilization across projects and sites",
            "Maintenance schedules, inspections, work orders, and compliance reminders",
            "Fuel, mileage, and operating cost capture with grant and programme allocation",
            "Drivers, routes, and trip visibility for distributed field operations",
            "Integration with procurement, inventory, and approval workflows",
            "Fleet spend vs budget dashboards and variance reporting",
        ],
        "feature_groups": [
            {
                "heading": "Assets & assignments",
                "items": [
                    "Vehicle profiles, registration, and insurance renewals",
                    "Assignment to projects, offices, or drivers",
                    "Utilisation and idle-time reporting",
                    "Cost allocation to grants and programs",
                ],
            },
            {
                "heading": "Maintenance & compliance",
                "items": [
                    "Preventive schedules and service history",
                    "Inspection checklists and defect tracking",
                    "Work orders linked to parts inventory",
                    "Compliance reminders for licenses and safety",
                ],
            },
            {
                "heading": "Operations & costs",
                "items": [
                    "Fuel purchases, consumption, and variance analysis",
                    "Mileage and trip logs with optional GPS interfaces",
                    "Driver licensing and training records",
                    "Dashboards for fleet spend vs budget",
                ],
            },
        ],
    },
    {
        "slug": "ai-auditor",
        "index": 5,
        "title": "AI Auditor",
        "tagline": "Continuous assurance, anomaly detection, and compliance monitoring across finance and operations.",
        "icon": "mi-sparkles",
        "meta_description": (
            "Sugna AI Auditor: anomaly detection, duplicate checks, compliance monitoring, "
            "risk indicators, and prioritized review for finance and audit teams."
        ),
        "summary_bullets": [
            "Continuous monitoring of transactions and patterns across modules",
            "Duplicate and near-duplicate detection across entities and periods",
            "Rules-based compliance alerts and configurable thresholds",
            "Risk-ranked worklists and exception queues for reviewers",
            "Fraud and anomaly indicators for finance and internal audit teams",
            "Evidence and assurance outputs aligned to donor and statutory audits",
        ],
        "feature_groups": [
            {
                "heading": "Detection & rules",
                "items": [
                    "Pattern-based alerts across journals, payments, and master data",
                    "Duplicate and near-duplicate transaction scoring",
                    "Configurable thresholds by account, project, or donor",
                    "Continuous monitoring rather than sample-only testing",
                ],
            },
            {
                "heading": "Risk & workflow",
                "items": [
                    "Risk-ranked worklists for reviewers and auditors",
                    "Exception routing with comments and resolution status",
                    "Linkage to supporting documents and approvals",
                    "Trend views for recurring issues or control gaps",
                ],
            },
            {
                "heading": "Reporting & assurance",
                "items": [
                    "Management and board-ready assurance summaries",
                    "Evidence packs for external audit coordination",
                    "Integration with financial and procurement modules",
                    "Audit trail of AI-assisted findings and human decisions",
                ],
            },
        ],
    },
    {
        "slug": "hospital-management",
        "index": 6,
        "title": "Hospital Management",
        "tagline": "Clinical, revenue, and stock workflows aligned to finance, compliance, and accreditation needs.",
        "icon": "mi-hospital",
        "meta_description": (
            "Sugna Hospital Management: patient flow, scheduling, pharmacy, lab, billing, inventory, "
            "and finance integration for healthcare providers."
        ),
        "summary_bullets": [
            "Patient registration, visits, and master patient index",
            "Appointments, scheduling, and care team assignment",
            "Clinical rosters and workforce visibility tied to HR where needed",
            "Pharmacy dispensing, stock control, and consumption tracking",
            "Laboratory orders, results workflow, and turnaround visibility",
            "Billing, collections, and revenue cycle discipline",
            "Medical inventory, consumption, and traceability for regulated items",
            "Finance integration for revenue recognition, costing, and management reporting",
        ],
        "feature_groups": [
            {
                "heading": "Patient & clinical front office",
                "items": [
                    "Registration, visits, and master patient index",
                    "Appointments, queues, and referral tracking",
                    "Clinical documentation hooks and care team assignment",
                    "Integration with billing and insurance where applicable",
                ],
            },
            {
                "heading": "Pharmacy, lab & diagnostics",
                "items": [
                    "Dispensing with stock deduction and alerts",
                    "Lab orders, results entry, and turnaround tracking",
                    "Medical supplies and consumption by department",
                    "Barcode and batch traceability for regulated items",
                ],
            },
            {
                "heading": "Revenue & finance alignment",
                "items": [
                    "Billing rules, packages, and payment plans",
                    "AR, collections, and cashiering",
                    "Revenue recognition and costing to finance",
                    "Management reporting for clinical and financial KPIs",
                ],
            },
        ],
    },
    {
        "slug": "corporate-management",
        "index": 7,
        "title": "Sugna Corporate Management",
        "tagline": "Group governance, consolidation, and executive oversight for multi-entity and multi-country organizations.",
        "icon": "mi-building",
        "meta_description": (
            "Sugna Corporate Management: group structure, consolidation, executive dashboards, "
            "policies, and strategic alignment across subsidiaries and programs."
        ),
        "summary_bullets": [
            "Legal entities, subsidiaries, consolidation scopes, and reporting lines",
            "Group consolidation, intercompany elimination, and management reporting",
            "Executive dashboards, KPIs, and board-ready packs",
            "Group-wide policies, controls, and delegated authorities",
            "Strategic planning aligned to programmes, budgets, and grants",
            "Risk and compliance roll-ups for leadership across entities",
            "Single source of truth for HQ and field alignment",
        ],
        "feature_groups": [
            {
                "heading": "Group structure & governance",
                "items": [
                    "Legal entities, ownership, and consolidation scopes",
                    "Reporting lines and delegated authorities",
                    "Group policies and exception tracking",
                    "Cross-entity workflows and approvals",
                ],
            },
            {
                "heading": "Consolidation & performance",
                "items": [
                    "Management and statutory consolidation paths",
                    "Intercompany eliminations and matching",
                    "KPIs spanning finance, operations, and programs",
                    "Executive and board reporting packs",
                ],
            },
            {
                "heading": "Strategy & alignment",
                "items": [
                    "Planning cycles linked to budgets and grants",
                    "Roadmap visibility across modules and entities",
                    "Risk and compliance roll-ups for leadership",
                    "Single source of truth for HQ and field alignment",
                ],
            },
        ],
    },
]

MODULE_PAGES_BY_SLUG: dict[str, ModulePage] = {m["slug"]: m for m in MODULE_PAGES_ORDERED}
