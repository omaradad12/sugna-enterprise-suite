from __future__ import annotations

import logging

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.generic import TemplateView

from .forms import ContactForm, DemoRequestForm
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


class SolutionsView(TemplateView):
    template_name = "website/solutions.html"


class IndustriesView(TemplateView):
    template_name = "website/industries.html"


class PricingView(TemplateView):
    template_name = "website/pricing.html"


class TrainingView(TemplateView):
    template_name = "website/training.html"


class SupportView(TemplateView):
    template_name = "website/support.html"


class LoginPortalView(TemplateView):
    template_name = "website/login_portal.html"


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
