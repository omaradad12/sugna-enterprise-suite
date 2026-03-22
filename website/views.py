from __future__ import annotations

import logging

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.generic import TemplateView

from .forms import ContactForm, DemoRequestForm

logger = logging.getLogger(__name__)


def _flash_form_success(request, title: str, data: dict) -> None:
    messages.success(
        request,
        f"{title} received. Our team will respond shortly.",
    )
    logger.info("website form submission: %s | %s", title, {k: v for k, v in data.items() if k != "message"})


class HomeView(TemplateView):
    template_name = "website/home.html"


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


def demo_request_view(request):
    if request.method == "POST":
        form = DemoRequestForm(request.POST)
        if form.is_valid():
            _flash_form_success(request, "Demo request", form.cleaned_data)
            return redirect("website:demo_request")
    else:
        form = DemoRequestForm()
    return render(request, "website/demo_request.html", {"form": form})


def contact_view(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            _flash_form_success(request, "Contact message", form.cleaned_data)
            return redirect("website:contact")
    else:
        form = ContactForm()
    return render(request, "website/contact.html", {"form": form})
