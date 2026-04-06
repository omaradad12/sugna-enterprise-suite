from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.mail import send_mail

from platform_email_templates.models import PlatformEmailTemplate

if TYPE_CHECKING:
    from platform_announcements.models import PlatformAnnouncement
    from tenants.models import Tenant

logger = logging.getLogger(__name__)

PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

# Supported merge fields (documented for authors and sample preview).
DOCUMENTED_VARIABLE_KEYS = [
    "tenant_name",
    "tenant_domain",
    "announcement_title",
    "announcement_message",
    "invoice_number",
    "amount",
    "due_date",
    "plan_name",
]


def default_sample_context() -> dict[str, str]:
    return {
        "tenant_name": "Demo Organization",
        "tenant_domain": "demo.example.com",
        "announcement_title": "Scheduled maintenance",
        "announcement_message": "We will perform maintenance on Sunday at 02:00 UTC.",
        "invoice_number": "INV-2026-00142",
        "amount": "1,250.00 USD",
        "due_date": "2026-04-15",
        "plan_name": "Enterprise",
    }


def render_template_text(text: str, context: dict[str, str]) -> str:
    """Replace {{ variable }} placeholders; unknown keys become empty strings."""

    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        return str(context.get(key, ""))

    return PLACEHOLDER_RE.sub(repl, text)


def render_platform_email_template(
    template: PlatformEmailTemplate,
    context: dict[str, str] | None = None,
) -> tuple[str, str]:
    base = default_sample_context()
    if context:
        base.update({k: str(v) for k, v in context.items()})
    subj = render_template_text(template.subject, base)
    body = render_template_text(template.body, base)
    return subj, body


def resolve_announcement_template(ann: "PlatformAnnouncement") -> PlatformEmailTemplate | None:
    """Template for announcement emails: explicit FK or built-in platform_announcement."""
    t = getattr(ann, "email_template_id", None) and ann.email_template
    if t and t.status == PlatformEmailTemplate.Status.ACTIVE:
        return t
    return (
        PlatformEmailTemplate.objects.filter(
            code="platform_announcement",
            status=PlatformEmailTemplate.Status.ACTIVE,
        )
        .first()
    )


def build_announcement_context(tenant: "Tenant", ann: "PlatformAnnouncement") -> dict[str, str]:
    plan = (getattr(tenant, "plan", None) or "").strip() or "—"
    return {
        "tenant_name": tenant.name,
        "tenant_domain": tenant.domain,
        "announcement_title": ann.title,
        "announcement_message": ann.message,
        "plan_name": plan,
        "invoice_number": "",
        "amount": "",
        "due_date": "",
    }


def recipient_emails_for_tenant(tenant: "Tenant") -> list[str]:
    """Tenant admin / notification inboxes from tenant DB (best-effort)."""
    from tenants.db import ensure_tenant_db_configured

    try:
        from tenant_users.models import TenantUser
    except Exception:
        return []

    alias = ensure_tenant_db_configured(tenant)
    if not getattr(tenant, "db_name", None):
        return []

    try:
        qs = (
            TenantUser.objects.using(alias)
            .filter(is_active=True, email_notifications=True)
            .order_by("-is_tenant_admin", "email")
        )
        return list(qs.values_list("email", flat=True).distinct()[:20])
    except Exception as exc:
        logger.warning("recipient_emails_for_tenant failed tenant=%s: %s", tenant.pk, exc)
        return []


def send_announcement_emails(ann: "PlatformAnnouncement") -> int:
    """
    Send announcement email to matching tenants using the linked (or default) template.
    Returns number of messages handed to the email backend.
    """
    from platform_announcements.services import iter_tenants_for_announcement

    tpl = resolve_announcement_template(ann)
    if not tpl:
        logger.warning("send_announcement_emails: no active template for announcement id=%s", ann.pk)
        return 0

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or "noreply@localhost"
    sent = 0
    for tenant in iter_tenants_for_announcement(ann):
        ctx = build_announcement_context(tenant, ann)
        subject, body = render_platform_email_template(tpl, ctx)
        recipients = recipient_emails_for_tenant(tenant)
        if not recipients:
            logger.info(
                "announcement id=%s skip tenant id=%s (no recipient emails)",
                ann.pk,
                tenant.pk,
            )
            continue
        try:
            send_mail(
                subject,
                body,
                from_email,
                recipients,
                fail_silently=False,
            )
            sent += 1
        except Exception as exc:
            logger.exception(
                "announcement id=%s send failed for tenant id=%s: %s",
                ann.pk,
                tenant.pk,
                exc,
            )
    return sent


def send_test_email(
    template: PlatformEmailTemplate,
    to_email: str,
    context: dict[str, str] | None = None,
) -> None:
    subject, body = render_platform_email_template(template, context)
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or "noreply@localhost"
    send_mail(
        f"[Test] {subject}",
        body,
        from_email,
        [to_email],
        fail_silently=False,
    )
