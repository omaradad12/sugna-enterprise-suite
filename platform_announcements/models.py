from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class PlatformAnnouncement(models.Model):
    """
    Control-plane broadcast to tenants (stored in default/public database).
    Targeting uses Tenant and Module rows from the same database.
    """

    class Category(models.TextChoices):
        SYSTEM_UPDATE = "system_update", "System update"
        BILLING = "billing", "Billing"
        SECURITY = "security", "Security"
        GENERAL = "general", "General"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class TargetingMode(models.TextChoices):
        ALL_TENANTS = "all", "All tenants"
        SELECTED_TENANTS = "selected", "Selected tenants"
        BY_MODULE = "by_module", "Tenants by module"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    title = models.CharField(max_length=255)
    message = models.TextField(help_text="Full message; shown in banner, popup, and announcement panel.")
    category = models.CharField(
        max_length=32,
        choices=Category.choices,
        default=Category.GENERAL,
        db_index=True,
    )
    priority = models.CharField(
        max_length=16,
        choices=Priority.choices,
        default=Priority.MEDIUM,
        db_index=True,
    )
    targeting_mode = models.CharField(
        max_length=16,
        choices=TargetingMode.choices,
        default=TargetingMode.ALL_TENANTS,
    )
    target_tenants = models.ManyToManyField(
        "tenants.Tenant",
        blank=True,
        related_name="platform_announcements_targeted",
        help_text="Used when targeting is «Selected tenants».",
    )
    target_modules = models.ManyToManyField(
        "tenants.Module",
        blank=True,
        related_name="platform_announcements_by_module",
        help_text="Used when targeting is «Tenants by module» (tenant has module enabled).",
    )
    start_at = models.DateTimeField(
        db_index=True,
        help_text="Announcement is visible from this time (inclusive).",
    )
    end_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Optional; leave empty for open-ended after start.",
    )
    send_email = models.BooleanField(default=False, help_text="Send email when published (requires mail configuration).")
    email_template = models.ForeignKey(
        "platform_email_templates.PlatformEmailTemplate",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="announcements",
        help_text="Optional; defaults to the «Platform announcement» system template when empty.",
    )
    show_popup = models.BooleanField(default=False)
    show_dashboard_banner = models.BooleanField(default=False)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="platform_announcements_created",
    )

    class Meta:
        ordering = ["-start_at", "-id"]
        indexes = [
            models.Index(fields=["status", "start_at", "end_at"]),
        ]

    def __str__(self) -> str:
        return self.title

    def display_status(self) -> str:
        """Human-readable lifecycle for admin list (Draft / Scheduled / Active / Expired)."""
        if self.status == self.Status.DRAFT:
            return "Draft"
        now = timezone.now()
        if self.start_at > now:
            return "Scheduled"
        if self.end_at and self.end_at < now:
            return "Expired"
        return "Active"

    def is_visible_now(self) -> bool:
        if self.status != self.Status.PUBLISHED:
            return False
        now = timezone.now()
        if self.start_at > now:
            return False
        if self.end_at and self.end_at < now:
            return False
        return True
