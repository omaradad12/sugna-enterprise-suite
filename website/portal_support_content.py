"""Customer Portal Support (support-center) marketing page — options, FAQ, SLA, contact."""

from __future__ import annotations

from typing import TypedDict


class SupportOption(TypedDict):
    slug: str
    title: str
    description: str
    icon: str
    cta_label: str
    href_key: str


class FAQItem(TypedDict):
    question: str
    answer: str


class SLARow(TypedDict):
    priority: str
    initial_response: str
    resolution_target: str


class ContactChannel(TypedDict):
    label: str
    value: str
    note: str
    href_key: str


SUP_LEAD = (
    "Access technical assistance, onboarding guidance, SLA details, and help resources for Sugna Enterprise Suite."
)

SUP_PORTAL_NOTE = (
    "Full self-service ticketing, live SLA dashboards, and status subscriptions open in your "
    "signed-in customer portal when enabled for your tenant."
)

SUP_OPTIONS: list[SupportOption] = [
    {
        "slug": "submit-ticket",
        "title": "Submit ticket",
        "description": "Report technical or configuration issues to the Sugna support team.",
        "icon": "mi-mail",
        "cta_label": "Contact support",
        "href_key": "contact",
    },
    {
        "slug": "knowledge-base",
        "title": "Knowledge base",
        "description": (
            "Browse guides for Finance, Grants, HR, Procurement, and system administration."
        ),
        "icon": "mi-grid",
        "cta_label": "Browse guides",
        "href_key": "kb",
    },
    {
        "slug": "training-onboarding",
        "title": "Training & onboarding",
        "description": "Request guided onboarding and user training sessions.",
        "icon": "mi-graduation",
        "cta_label": "View training",
        "href_key": "training",
    },
    {
        "slug": "sla-information",
        "title": "SLA information",
        "description": "Review support response times and service level commitments.",
        "icon": "mi-clipboard-check",
        "cta_label": "View SLA",
        "href_key": "fragment_sla",
    },
    {
        "slug": "system-status",
        "title": "System status",
        "description": "Check availability and scheduled maintenance updates.",
        "icon": "mi-monitor",
        "cta_label": "View status",
        "href_key": "fragment_status",
    },
]

SUP_FAQ: list[FAQItem] = [
    {
        "question": "How do I submit a support ticket?",
        "answer": (
            "Use Contact support to send a message with impact, module, and steps to reproduce. "
            "Signed-in tenants can submit tickets inside the Organization Workspace with tenant context attached."
        ),
    },
    {
        "question": "What information should I include for faster resolution?",
        "answer": (
            "Include environment (tenant name if applicable), affected module, error text or screenshots, "
            "time of occurrence, and whether the issue blocks payroll, reporting, or donor reporting."
        ),
    },
    {
        "question": "How do training and onboarding requests work?",
        "answer": (
            "Training & onboarding links to public learning paths and webinars. Dedicated sessions are scheduled "
            "with your Sugna account team based on your subscription and rollout plan."
        ),
    },
    {
        "question": "Where can I see response times and commitments?",
        "answer": (
            "The SLA section on this page summarizes standard targets. Your order form or enterprise agreement "
            "may define additional terms for your organization."
        ),
    },
    {
        "question": "How is system status communicated?",
        "answer": (
            "Planned maintenance is announced in advance where possible. After sign-in, your portal can show "
            "live availability and incident updates for your environment."
        ),
    },
]

SUP_SLA_ROWS: list[SLARow] = [
    {
        "priority": "P1 — Critical (production down)",
        "initial_response": "4 business hours",
        "resolution_target": "1 business day (workaround or fix per runbook)",
    },
    {
        "priority": "P2 — High (major feature impaired)",
        "initial_response": "1 business day",
        "resolution_target": "5 business days",
    },
    {
        "priority": "P3 — Standard",
        "initial_response": "2 business days",
        "resolution_target": "10 business days",
    },
    {
        "priority": "P4 — Low / advisory",
        "initial_response": "5 business days",
        "resolution_target": "Best effort",
    },
]

SUP_CONTACT_CHANNELS: list[ContactChannel] = [
    {
        "label": "Contact form",
        "value": "Sales, partnerships, and general inquiries",
        "note": "Use the site contact form for new requests; existing customers should follow the channel in their contract.",
        "href_key": "contact",
    },
    {
        "label": "Support hub",
        "value": "Help center and product support overview",
        "note": "See the main Support page for channels and escalation paths.",
        "href_key": "support",
    },
]

SUP_CONTACT_HOURS = (
    "Regional coverage hours are aligned to your subscription. Critical (P1) routing follows your enterprise agreement."
)
