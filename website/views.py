from __future__ import annotations

import logging

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.generic import TemplateView

from .forms import ContactForm, DemoRequestForm
from .industry_cards import INDUSTRY_CARDS
from .knowledge_base_content import KB_CATEGORIES, KB_LEAD
from .portal_support_content import (
    SUP_CONTACT_CHANNELS,
    SUP_CONTACT_HOURS,
    SUP_FAQ,
    SUP_OPTIONS,
    SUP_PORTAL_NOTE,
    SUP_SLA_ROWS,
    SUP_LEAD,
)
from .portal_templates_content import TPL_ACCOUNT_NOTE, TPL_CATEGORIES, TPL_LEAD, TPL_STANDARDS
from .module_pages import MODULE_PAGES_BY_SLUG, MODULE_PAGES_ORDERED
from .mail_notify import format_contact_email, format_demo_request_email, send_website_notification

logger = logging.getLogger(__name__)


def _flash_form_success(request, title: str, data: dict, *, email_subject: str, email_body: str) -> None:
    messages.success(
        request,
        f"{title} received. Our team will respond shortly.",
    )
    logger.info("website form submission: %s | %s", title, {k: v for k, v in data.items() if k != "message"})
    send_website_notification(subject=email_subject, body=email_body)


class HomeView(TemplateView):
    template_name = "website/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["demo_form"] = DemoRequestForm()
        return ctx


class AboutView(TemplateView):
    template_name = "website/about.html"


class ModulesView(TemplateView):
    template_name = "website/modules.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["module_pages"] = MODULE_PAGES_ORDERED
        return ctx


class ModuleDetailView(TemplateView):
    """Per-module marketing page with grouped feature detail."""

    template_name = "website/module_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        slug = (self.kwargs.get("slug") or "").strip()
        page = MODULE_PAGES_BY_SLUG.get(slug)
        if not page:
            raise Http404("Module not found")
        ctx["module"] = page
        return ctx


class PlatformView(TemplateView):
    """Enterprise platform overview (ActivityInfo-style marketing page)."""

    template_name = "website/platform.html"


class SolutionsView(TemplateView):
    template_name = "website/solutions.html"


class IndustriesView(TemplateView):
    template_name = "website/industries.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["industry_cards"] = INDUSTRY_CARDS
        return ctx


class PricingSubscriptionsView(TemplateView):
    template_name = "website/pricing_subscriptions.html"


class PricingOnboardingView(TemplateView):
    template_name = "website/pricing_onboarding.html"


class TrainingView(TemplateView):
    template_name = "website/training.html"


class TrainingRoleBasedView(TemplateView):
    template_name = "website/training_role_based.html"


class TrainingWebinarsView(TemplateView):
    template_name = "website/training_webinars.html"


class TrainingCertificationView(TemplateView):
    template_name = "website/training_certification.html"


class TrainingSupportView(TemplateView):
    """Training-side support (schedules, access, escalation) — distinct from site Support hub."""

    template_name = "website/training_support.html"


class ResourcesView(TemplateView):
    """Hub for documentation, blog, legal, and downloads (marketing)."""

    template_name = "website/resources.html"


class SupportView(TemplateView):
    template_name = "website/support.html"


CUSTOMER_PORTAL_SECTIONS: dict[str, dict[str, str]] = {
    "my-organization": {
        "title": "My Organization",
        "description": (
            "Maintain your legal profile, program structure, branding, and key contacts so audits, "
            "donors, and partners see a consistent, trustworthy organization record."
        ),
    },
    "subscription-billing": {
        "title": "Subscription & Billing",
        "description": (
            "Review your plan, module entitlements, invoices, payment methods, and renewal terms "
            "in one place—aligned to institutional procurement."
        ),
    },
    "modules": {
        "title": "Modules",
        "description": (
            "See which capabilities are enabled for your workspace — Financial & Grant Management, "
            "Human Resource Management, Procurement & Logistics, Fleet Management, AI Auditor, "
            "Hospital Management, and Sugna Corporate Management."
        ),
    },
    "users-access": {
        "title": "Users & Access",
        "description": (
            "Govern who can sign in, which roles they hold, and how segregation of duties is preserved "
            "across HQ and field offices."
        ),
    },
    "support-center": {
        "title": "Support",
        "description": (
            "Contact support, submit a ticket, review SLA information, and browse help resources "
            "for your Organization Workspace."
        ),
    },
    "knowledge-base": {
        "title": "Knowledge Base",
        "description": (
            "User guides for Finance, Grants, HR, Procurement, AI Auditor, and general system usage."
        ),
    },
    "templates": {
        "title": "Templates",
        "description": (
            "Professional template packs for finance, grants, HR, procurement, compliance, and hospital operations."
        ),
    },
    "security-settings": {
        "title": "Security Settings",
        "description": (
            "Multi-factor authentication, password policy, sessions, data handling, and audit trail access "
            "for regulated environments."
        ),
    },
    "notifications": {
        "title": "Notifications",
        "description": (
            "Control in-app alerts, email and SMS channels, digests, and quiet hours for distributed teams."
        ),
    },
    "training-onboarding": {
        "title": "Training & Onboarding",
        "description": (
            "Learning paths, live sessions, sandbox options, and completion records for donor assurance."
        ),
    },
    "system-updates": {
        "title": "System Updates",
        "description": (
            "Release highlights, maintenance windows, deprecations, and roadmap feedback for your sector."
        ),
    },
}


class LoginPortalView(TemplateView):
    template_name = "website/login_portal.html"


class CustomerPortalAccessView(TemplateView):
    """Choose Organization Workspace vs Platform Administration (Dynamics-style access hub)."""

    template_name = "website/customer_portal_access.html"


class CustomerPortalDashboardView(TemplateView):
    """Marketing preview of the signed-in customer dashboard (card-based SaaS layout)."""

    template_name = "website/customer_portal_dashboard.html"


def _support_center_option_hrefs() -> dict[str, str]:
    return {
        "contact": reverse("website:contact"),
        "kb": reverse("website:customer_portal_section", kwargs={"slug": "knowledge-base"}),
        "training": reverse("website:training"),
        "fragment_sla": "#cp-support-sla",
        "fragment_status": "#cp-support-status",
    }


class CustomerPortalSectionView(TemplateView):
    """Single informational page per customer-portal menu slug."""

    template_name = "website/customer_portal_section.html"

    def get_template_names(self):
        slug = (self.kwargs.get("slug") or "").strip()
        if slug == "knowledge-base":
            return ["website/customer_portal_knowledge_base.html"]
        if slug == "templates":
            return ["website/customer_portal_templates.html"]
        if slug == "support-center":
            return ["website/customer_portal_support_center.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        slug = self.kwargs.get("slug") or ""
        meta = CUSTOMER_PORTAL_SECTIONS.get(slug)
        if not meta:
            raise Http404("Page not found")
        ctx["cp_slug"] = slug
        ctx["cp_title"] = meta["title"]
        ctx["cp_description"] = meta["description"]
        if slug == "knowledge-base":
            ctx["kb_categories"] = KB_CATEGORIES
            ctx["kb_lead"] = KB_LEAD
        if slug == "templates":
            ctx["tpl_categories"] = TPL_CATEGORIES
            ctx["tpl_lead"] = TPL_LEAD
            ctx["tpl_standards"] = TPL_STANDARDS
            ctx["tpl_account_note"] = TPL_ACCOUNT_NOTE
        if slug == "support-center":
            hrefs = _support_center_option_hrefs()
            ctx["sup_options"] = [
                {
                    "slug": o["slug"],
                    "title": o["title"],
                    "description": o["description"],
                    "icon": o["icon"],
                    "cta_label": o["cta_label"],
                    "href": hrefs[o["href_key"]],
                }
                for o in SUP_OPTIONS
            ]
            ctx["sup_lead"] = SUP_LEAD
            ctx["sup_portal_note"] = SUP_PORTAL_NOTE
            ctx["sup_faq"] = SUP_FAQ
            ctx["sup_sla_rows"] = SUP_SLA_ROWS
            ctx["sup_contact_hours"] = SUP_CONTACT_HOURS
            ctx["sup_contact_channels"] = [
                {
                    "label": ch["label"],
                    "value": ch["value"],
                    "note": ch["note"],
                    "href": reverse(f"website:{ch['href_key']}"),
                }
                for ch in SUP_CONTACT_CHANNELS
            ]
        return ctx


class FeaturesView(TemplateView):
    template_name = "website/features.html"


class BlogView(TemplateView):
    template_name = "website/blog.html"


class PrivacyView(TemplateView):
    template_name = "website/privacy.html"


class TermsView(TemplateView):
    template_name = "website/terms.html"


def page_not_found_view(request, exception):
    return render(request, "website/404.html", status=404)


def demo_request_view(request):
    if request.method == "POST":
        form = DemoRequestForm(request.POST)
        if form.is_valid():
            _flash_form_success(
                request,
                "Demo request",
                form.cleaned_data,
                email_subject="Demo request",
                email_body=format_demo_request_email(form.cleaned_data),
            )
            return redirect("website:demo_request")
    else:
        form = DemoRequestForm()
    return render(request, "website/demo_request.html", {"form": form})


def contact_view(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            _flash_form_success(
                request,
                "Contact message",
                form.cleaned_data,
                email_subject="Contact form",
                email_body=format_contact_email(form.cleaned_data),
            )
            return redirect("website:contact")
    else:
        form = ContactForm()
    return render(request, "website/contact.html", {"form": form})
