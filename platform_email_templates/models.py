from __future__ import annotations

from django.db import models


class PlatformEmailTemplate(models.Model):
    """
    Control-plane reusable email (subject + body) with {{ variable }} placeholders.
    """

    class Category(models.TextChoices):
        SYSTEM = "system", "System"
        TENANT = "tenant", "Tenant"
        BILLING = "billing", "Billing"
        SUPPORT = "support", "Support"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    code = models.SlugField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="Stable key for integrations (e.g. platform_announcement).",
    )
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=16, choices=Category.choices, default=Category.SYSTEM, db_index=True)
    subject = models.CharField(max_length=255, help_text="Supports {{ variable }} placeholders.")
    body = models.TextField(help_text="Email body; supports {{ variable }} placeholders.")
    variables = models.JSONField(
        default=list,
        blank=True,
        help_text="List of variable names documented for this template (e.g. tenant_name, amount).",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    is_system = models.BooleanField(
        default=False,
        help_text="Built-in template; cannot be deleted.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "name"]

    def __str__(self) -> str:
        return self.name

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE
