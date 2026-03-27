"""
Transaction setup chain: Donor → Project → Project grant → Budget → Transactions.

Used to block operational entry points with friendly guidance (not raw DB errors).
"""

from __future__ import annotations

from dataclasses import dataclass

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _


@dataclass(frozen=True)
class MissingSetupStep:
    """First missing step in the setup chain."""

    slug: str
    headline: str
    body: str
    action_label: str
    setup_url: str


def get_first_missing_transaction_prerequisite(using: str) -> MissingSetupStep | None:
    """
    Return the first incomplete step for the tenant DB, or None if the chain is satisfied.

    Budget: at least one budget line on an active grant (grant-level programme budget).
    """
    from tenant_grants.models import BudgetLine, Donor, Grant, Project

    if not Donor.objects.using(using).filter(status=Donor.Status.ACTIVE).exists():
        return MissingSetupStep(
            slug="donor",
            headline=_("Start with your donors"),
            body=_(
                "Before you record receipts, payments, or other transactions, add at least one "
                "active donor. Donors come first, then projects, project grants, and budgets."
            ),
            action_label=_("Go to Donors"),
            setup_url=reverse("tenant_portal:grants_donors"),
        )

    if not Project.objects.using(using).filter(
        is_active=True, status=Project.Status.ACTIVE
    ).exists():
        return MissingSetupStep(
            slug="project",
            headline=_("Add a project"),
            body=_(
                "Create an active project so project grants and budgets can be linked to a programme. "
                "Projects sit between donors and project grants in your setup."
            ),
            action_label=_("Go to Projects"),
            setup_url=reverse("tenant_portal:grants_projects_list"),
        )

    if not Grant.objects.using(using).filter(status=Grant.Status.ACTIVE).exists():
        return MissingSetupStep(
            slug="grant_agreement",
            headline=_("Activate a project grant"),
            body=_(
                "You need at least one active project grant before financial transactions can tie "
                "to funding rules, receivables, and reporting."
            ),
            action_label=_("Go to Project grants"),
            setup_url=reverse("tenant_portal:grants_grants"),
        )

    if not BudgetLine.objects.using(using).filter(grant__status=Grant.Status.ACTIVE).exists():
        return MissingSetupStep(
            slug="budget",
            headline=_("Add grant budget lines"),
            body=_(
                "Set up budget lines for your active grants so spending and income stay within "
                "approved limits. Budget lines complete the path before day-to-day transactions."
            ),
            action_label=_("Go to Grant budgets"),
            setup_url=reverse("tenant_portal:grants_budgets"),
        )

    return None


def render_if_setup_incomplete_for_transactions(
    request: HttpRequest,
    *,
    page_title: str,
    active_submenu: str | None = None,
    active_item: str | None = None,
) -> HttpResponse | None:
    """If setup is incomplete, return a full-page guided response; otherwise None."""
    step = get_first_missing_transaction_prerequisite(request.tenant_db)
    if step is None:
        return None
    ctx = {
        "tenant": request.tenant,
        "tenant_user": request.tenant_user,
        "missing_step": step,
        "page_title": page_title,
        "active_submenu": active_submenu,
        "active_item": active_item,
    }
    return render(request, "tenant_portal/setup_prerequisite_required.html", ctx)
