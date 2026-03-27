"""
Customer portal sitemap: sections, professional subpages, and URL resolution.

URL pattern (tenant routes, prefix /t/): portal/, portal/<section>/, portal/<section>/<page>/
Designed for NGOs, humanitarian organizations, hospitals, and institutions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.urls import NoReverseMatch, reverse


@dataclass(frozen=True)
class PortalPageDef:
    """One leaf page under a customer-portal section."""

    id: str
    label: str
    description: str
    redirect_url_name: str | None = None
    """
    If set, customer_portal_page view redirects to this named URL (operational ERP screen).
    Otherwise the portal stub page is shown for the URL portal/<section>/<page>/.
    """


@dataclass(frozen=True)
class PortalSectionDef:
    id: str
    label: str
    subtitle: str
    icon: str
    pages: tuple[PortalPageDef, ...]


PORTAL_SECTIONS: tuple[PortalSectionDef, ...] = (
    PortalSectionDef(
        id="dashboard",
        label="Dashboard",
        subtitle="Your workspace overview, tasks, and key metrics.",
        icon="layout",
        pages=(
            PortalPageDef(
                id="overview",
                label="Home overview",
                description="Tenant home with enabled modules, subscription summary, and quick entry to operations.",
                redirect_url_name="tenant_portal:home",
            ),
            PortalPageDef(
                id="activity",
                label="Activity & approvals",
                description="Pending approvals, recent postings, and items awaiting your action across finance and grants.",
                redirect_url_name="tenant_portal:finance_pending_approvals",
            ),
            PortalPageDef(
                id="kpis",
                label="Executive KPIs",
                description="Dashboard with liquidity, grants, and budget signals in one operational workspace.",
                redirect_url_name="tenant_portal:finance_home",
            ),
            PortalPageDef(
                id="shortcuts",
                label="Shortcuts & favorites",
                description="Pin frequently used reports, donors, and workflows for one-click access (coming soon).",
            ),
        ),
    ),
    PortalSectionDef(
        id="organization",
        label="My Organization",
        subtitle="Legal profile, structure, and mission context for audits and donors.",
        icon="briefcase",
        pages=(
            PortalPageDef(
                id="profile-identity",
                label="Profile & legal identity",
                description="Registered name, identifiers, fiscal year, and core organization attributes.",
                redirect_url_name="tenant_portal:organization_settings",
            ),
            PortalPageDef(
                id="branding",
                label="Branding & communications",
                description="Logo, letterhead defaults, and outward-facing identity for reports and portals.",
            ),
            PortalPageDef(
                id="sites-programs",
                label="Sites, locations & programs",
                description="Country offices, field sites, hubs, and program hierarchy for allocation and reporting.",
            ),
            PortalPageDef(
                id="structure",
                label="Departments & dimensions",
                description="Organizational structure aligned to finance dimensions and donor reporting.",
                redirect_url_name="tenant_portal:setup_cost_centers_list",
            ),
            PortalPageDef(
                id="contacts",
                label="Key contacts & signatories",
                description="Authorized signatories, banking contacts, and escalation owners.",
            ),
            PortalPageDef(
                id="documents",
                label="Document vault",
                description="Registration certificates, MOUs, bank mandates, and policy documents (centralized repository).",
                redirect_url_name="tenant_portal:documents_dashboard",
            ),
        ),
    ),
    PortalSectionDef(
        id="billing",
        label="Subscription & billing",
        subtitle="Plan, invoices, and commercial terms for your institution.",
        icon="credit-card",
        pages=(
            PortalPageDef(
                id="plan",
                label="Plan & entitlements",
                description="Active edition, module entitlements, and feature flags for your tenant.",
            ),
            PortalPageDef(
                id="invoices",
                label="Invoices & statements",
                description="Billing history, PDF invoices, and payment status for finance teams.",
            ),
            PortalPageDef(
                id="payment-methods",
                label="Payment methods",
                description="Cards, bank debit, and purchase-order billing where applicable.",
            ),
            PortalPageDef(
                id="usage",
                label="Usage & seats",
                description="Named users, peak usage, and storage or transaction envelopes.",
            ),
            PortalPageDef(
                id="contracts",
                label="Contracts & renewals",
                description="MSAs, order forms, renewal dates, and notice periods.",
            ),
        ),
    ),
    PortalSectionDef(
        id="modules",
        label="Modules",
        subtitle="What is enabled today and what you can add as programs grow.",
        icon="grid",
        pages=(
            PortalPageDef(
                id="enabled",
                label="Enabled modules",
                description="Modules active for this tenant and links into each operational area.",
                redirect_url_name="tenant_portal:home",
            ),
            PortalPageDef(
                id="catalog",
                label="Module catalog",
                description="Finance & grants, budgeting, cash, procurement, audit & risk, and more.",
            ),
            PortalPageDef(
                id="requests",
                label="Enable / disable requests",
                description="Formal requests for new modules or sandboxes for pilots and training.",
            ),
            PortalPageDef(
                id="dependencies",
                label="Dependencies & prerequisites",
                description="Setup steps, master data, and governance needed before enabling a module.",
            ),
        ),
    ),
    PortalSectionDef(
        id="users-access",
        label="Users & access",
        subtitle="Who can sign in, what they can do, and evidence for audits.",
        icon="users",
        pages=(
            PortalPageDef(
                id="users",
                label="Users",
                description="Invite, activate, and offboard users across country offices and HQ.",
                redirect_url_name="tenant_portal:user_management",
            ),
            PortalPageDef(
                id="roles",
                label="Roles & permissions",
                description="Role templates mapped to segregation-of-duties for finance and grants.",
                redirect_url_name="tenant_portal:roles_permissions_list",
            ),
            PortalPageDef(
                id="groups",
                label="Groups & teams",
                description="Project teams, approval chains, and delegated responsibility groups.",
            ),
            PortalPageDef(
                id="partner-access",
                label="Partner & auditor access",
                description="Time-bound access for donors, auditors, and external partners.",
            ),
            PortalPageDef(
                id="reviews",
                label="Access reviews",
                description="Periodic certification of who holds sensitive roles (SOX-style and donor expectations).",
            ),
            PortalPageDef(
                id="sign-in-activity",
                label="Sign-in activity",
                description="Recent authentication events for security monitoring.",
                redirect_url_name="tenant_portal:audit_risk_user_activity",
            ),
        ),
    ),
    PortalSectionDef(
        id="support",
        label="Support Center",
        subtitle="Cases, response targets, and help for mission-critical operations.",
        icon="life-buoy",
        pages=(
            PortalPageDef(
                id="open-case",
                label="Open a case",
                description="Log severity, affected module, and attachments for the support team.",
            ),
            PortalPageDef(
                id="my-cases",
                label="My cases",
                description="Track status, owner, and resolution notes across your organization.",
            ),
            PortalPageDef(
                id="health",
                label="Service health",
                description="Platform availability, incident history, and scheduled maintenance.",
            ),
            PortalPageDef(
                id="sla",
                label="Severity & response targets",
                description="Definitions for P1–P4, hours of coverage, and escalation paths.",
            ),
            PortalPageDef(
                id="escalation",
                label="Escalation contacts",
                description="Named customer success and duty managers for emergencies.",
            ),
        ),
    ),
    PortalSectionDef(
        id="knowledge-base",
        label="Knowledge Base",
        subtitle="Guidance tailored to NGOs, humanitarian response, hospitals, and public institutions.",
        icon="book-open",
        pages=(
            PortalPageDef(
                id="getting-started",
                label="Getting started",
                description="First-month checklist: chart of accounts, donors, grants, and period close.",
            ),
            PortalPageDef(
                id="finance-grants",
                label="Finance & grants",
                description="Fund accounting, donor restrictions, utilization, and compliance reporting.",
            ),
            PortalPageDef(
                id="ngo-humanitarian",
                label="NGO & humanitarian",
                description="Multi-site operations, rapid response, and donor reporting in volatile contexts.",
            ),
            PortalPageDef(
                id="hospitals",
                label="Hospitals & service delivery",
                description="Cost centers, programs, and grant tracking for health institutions.",
            ),
            PortalPageDef(
                id="videos",
                label="Video tutorials",
                description="Short walkthroughs for vouchers, budgets, and grant lifecycle.",
            ),
            PortalPageDef(
                id="glossary",
                label="Glossary",
                description="Terms used across finance, grants, and compliance in Sugna.",
            ),
        ),
    ),
    PortalSectionDef(
        id="downloads",
        label="Templates",
        subtitle="Purchasable Standard and Professional packs, connectors, and offline-friendly assets.",
        icon="download",
        pages=(
            PortalPageDef(
                id="connectors",
                label="Desktop connectors",
                description="Excel add-ins, sync agents, and integration helpers where offered.",
            ),
            PortalPageDef(
                id="templates",
                label="Report & export templates",
                description="Standard layouts for donors, boards, and regulators.",
                redirect_url_name="tenant_portal:reporting_export_tools",
            ),
            PortalPageDef(
                id="mobile",
                label="Mobile apps",
                description="Approved mobile experiences for approvals and field capture.",
            ),
            PortalPageDef(
                id="offline",
                label="Offline packs",
                description="Forms and checklists for low-connectivity field operations.",
            ),
        ),
    ),
    PortalSectionDef(
        id="notifications",
        label="Notifications",
        subtitle="How and when the platform reaches your teams.",
        icon="bell",
        pages=(
            PortalPageDef(
                id="inbox",
                label="Notification center",
                description="In-app feed of alerts, tasks, and system messages.",
            ),
            PortalPageDef(
                id="financial-alerts",
                label="Financial alerts",
                description="Budget, liquidity, and compliance warnings surfaced to finance leads.",
                redirect_url_name="tenant_portal:finance_financial_alerts",
            ),
            PortalPageDef(
                id="channels",
                label="Delivery channels",
                description="Email, SMS, and webhook destinations per workflow.",
            ),
            PortalPageDef(
                id="digests",
                label="Subscriptions & digests",
                description="Daily or weekly summaries for leadership and program managers.",
            ),
            PortalPageDef(
                id="quiet-hours",
                label="Quiet hours",
                description="Respect field staff time zones and duty rosters.",
            ),
        ),
    ),
    PortalSectionDef(
        id="security",
        label="Security",
        subtitle="Identity, sessions, and audit readiness.",
        icon="shield",
        pages=(
            PortalPageDef(
                id="overview",
                label="Security overview",
                description="Tenant-level security posture summary and recommendations.",
            ),
            PortalPageDef(
                id="mfa",
                label="Multi-factor authentication",
                description="Enroll and manage MFA for your account.",
                redirect_url_name="tenant_portal:profile",
            ),
            PortalPageDef(
                id="password-policy",
                label="Password policy",
                description="Complexity, rotation, and lockout rules applied to tenant users.",
            ),
            PortalPageDef(
                id="sessions",
                label="Sessions & devices",
                description="Active sessions and trusted devices (where enabled).",
            ),
            PortalPageDef(
                id="data-residency",
                label="Data residency & retention",
                description="Where data is processed and retention commitments for your agreements.",
            ),
            PortalPageDef(
                id="audit-log",
                label="Financial audit trail",
                description="Immutable history of accounting changes for investigations and audits.",
                redirect_url_name="tenant_portal:finance_audit_trail",
            ),
        ),
    ),
    PortalSectionDef(
        id="integrations",
        label="Integrations",
        subtitle="Connect payroll, banking, ERP, and field systems responsibly.",
        icon="share-2",
        pages=(
            PortalPageDef(
                id="hub",
                label="Integration hub",
                description="Overview of connected systems and health indicators.",
                redirect_url_name="tenant_portal:integrations_home",
            ),
            PortalPageDef(
                id="webhooks",
                label="Webhooks",
                description="Outbound events, retries, and signing keys.",
                redirect_url_name="tenant_portal:integrations_webhooks",
            ),
            PortalPageDef(
                id="erp",
                label="ERP & finance systems",
                description="Connectors for external general ledgers and consolidation tools.",
                redirect_url_name="tenant_portal:integrations_erp",
            ),
            PortalPageDef(
                id="data-exchange",
                label="Data import & export",
                description="Bulk exchange schedules, formats, and validation rules.",
            ),
            PortalPageDef(
                id="partners",
                label="Partner connectors",
                description="Approved third-party apps and data processors.",
            ),
        ),
    ),
    PortalSectionDef(
        id="training",
        label="Training & onboarding",
        subtitle="Build capability across HQ, country offices, and partners.",
        icon="award",
        pages=(
            PortalPageDef(
                id="paths",
                label="Learning paths",
                description="Role-based curricula for finance, grants, and field managers.",
            ),
            PortalPageDef(
                id="webinars",
                label="Live webinars",
                description="Scheduled sessions with Q&A for new releases and donor rules.",
            ),
            PortalPageDef(
                id="sandbox",
                label="Sandbox tenant",
                description="Safe environment for rehearsals before go-live.",
            ),
            PortalPageDef(
                id="certifications",
                label="Completion records",
                description="Track training completion for audits and donor assurance.",
            ),
        ),
    ),
    PortalSectionDef(
        id="updates",
        label="System updates",
        subtitle="Release transparency for regulated and donor-funded environments.",
        icon="refresh-cw",
        pages=(
            PortalPageDef(
                id="whats-new",
                label="What’s new",
                description="Highlights per release with impact on finance, grants, and controls.",
            ),
            PortalPageDef(
                id="maintenance",
                label="Maintenance windows",
                description="Planned downtime and read-only periods.",
            ),
            PortalPageDef(
                id="deprecations",
                label="Deprecations",
                description="Features approaching end-of-life and migration guidance.",
            ),
            PortalPageDef(
                id="feedback",
                label="Roadmap feedback",
                description="Submit priorities for humanitarian, hospital, and institutional scenarios.",
            ),
        ),
    ),
    PortalSectionDef(
        id="profile",
        label="Profile",
        subtitle="Your identity, preferences, and delegation within the tenant.",
        icon="user",
        pages=(
            PortalPageDef(
                id="my-profile",
                label="My profile",
                description="Name, title, contact information, and photo.",
                redirect_url_name="tenant_portal:profile",
            ),
            PortalPageDef(
                id="preferences",
                label="Preferences",
                description="Defaults for locale, date format, and landing experience.",
                redirect_url_name="tenant_portal:profile",
            ),
            PortalPageDef(
                id="delegation",
                label="Delegation & out of office",
                description="Temporary approvers and coverage rules.",
            ),
            PortalPageDef(
                id="locale",
                label="Language & locale",
                description="Display language, time zone, and regional formats.",
            ),
        ),
    ),
)


def get_section(section_id: str) -> PortalSectionDef | None:
    for s in PORTAL_SECTIONS:
        if s.id == section_id:
            return s
    return None


def get_page(section_id: str, page_id: str) -> PortalPageDef | None:
    sec = get_section(section_id)
    if not sec:
        return None
    for p in sec.pages:
        if p.id == page_id:
            return p
    return None


def _safe_reverse(url_name: str) -> str | None:
    try:
        return reverse(url_name)
    except NoReverseMatch:
        return None


def href_for_page(section_id: str, page: PortalPageDef) -> str:
    if page.redirect_url_name:
        u = _safe_reverse(page.redirect_url_name)
        if u:
            return u
    return reverse("tenant_portal:customer_portal_page", kwargs={"section": section_id, "page": page.id})


def href_for_section(section_id: str) -> str:
    return reverse("tenant_portal:customer_portal_section", kwargs={"section": section_id})


def build_portal_sidebar_nav(current_section: str | None, current_page: str | None) -> list[dict[str, Any]]:
    """Nested nav for templates: href, active flags, children."""
    items: list[dict[str, Any]] = []
    for sec in PORTAL_SECTIONS:
        sec_active = current_section == sec.id
        section_href = href_for_section(sec.id)
        children: list[dict[str, Any]] = []
        for p in sec.pages:
            children.append(
                {
                    "id": p.id,
                    "label": p.label,
                    "href": href_for_page(sec.id, p),
                    "description": p.description,
                    "is_active": sec_active and current_page == p.id,
                    "is_external_route": bool(p.redirect_url_name),
                }
            )
        items.append(
            {
                "id": sec.id,
                "label": sec.label,
                "subtitle": sec.subtitle,
                "icon": sec.icon,
                "href": section_href,
                "is_section_landing_active": sec_active and not current_page,
                "is_expanded": sec_active,
                "children": children,
            }
        )
    return items


def portal_url_map() -> list[dict[str, str]]:
    """Flat reference for docs, onboarding, or API (path pattern + label)."""
    rows: list[dict[str, str]] = [{"path": "/t/portal/", "name": "Customer portal hub", "section": "", "page": ""}]
    for sec in PORTAL_SECTIONS:
        rows.append(
            {
                "path": f"/t/portal/{sec.id}/",
                "name": sec.label,
                "section": sec.id,
                "page": "",
            }
        )
        for p in sec.pages:
            rows.append(
                {
                    "path": f"/t/portal/{sec.id}/{p.id}/",
                    "name": f"{sec.label} — {p.label}",
                    "section": sec.id,
                    "page": p.id,
                }
            )
    return rows
