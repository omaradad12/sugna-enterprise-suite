"""Send website form submissions to a private inbox (configured via settings, never shown in templates)."""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def _recipient() -> str:
    return (getattr(settings, "WEBSITE_INBOUND_EMAIL", None) or "").strip()


def send_website_notification(*, subject: str, body: str) -> bool:
    """
    Deliver a plain-text message to WEBSITE_INBOUND_EMAIL.
    Returns True if send was attempted and succeeded; False if skipped or failed.
    """
    to = _recipient()
    if not to:
        logger.warning(
            "WEBSITE_INBOUND_EMAIL is not set; form notification not emailed. "
            "Set it in the environment to receive website messages."
        )
        return False

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or "webmaster@localhost"

    try:
        send_mail(
            subject=f"[Sugna website] {subject}",
            message=body,
            from_email=from_email,
            recipient_list=[to],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Failed to send website notification email to configured inbox.")
        return False

    logger.info("Website notification email sent (subject=%s).", subject)
    return True


def format_contact_email(data: dict[str, Any]) -> str:
    lines = [
        "New message from the website contact form.",
        "",
        f"Organization: {data.get('organization_name', '')}",
        f"Email: {data.get('email', '')}",
        f"Phone: {data.get('phone', '') or '—'}",
        "",
        "Message:",
        str(data.get("message", "") or ""),
        "",
        "---",
        "Reply to the visitor using the email address above.",
    ]
    return "\n".join(lines)


def format_demo_request_email(data: dict[str, Any]) -> str:
    lines = [
        "New demo request from the website.",
        "",
        f"Full name: {data.get('full_name', '')}",
        f"Email: {data.get('email', '')}",
        f"Organization: {data.get('organization_name', '')}",
        f"Phone: {data.get('phone', '') or '—'}",
        "",
        "Message:",
        str(data.get("message", "") or ""),
        "",
        "---",
        "Reply to the visitor using the email address above.",
    ]
    return "\n".join(lines)
