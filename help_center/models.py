"""
Platform-level Help Center: shared content and support tickets.
Stored in default (control-plane) DB; tenant users view content and submit tickets
linked to their tenant and user.
"""
from django.db import models


class HelpCategory(models.Model):
    """Category for organizing help content (e.g. Getting Started, Finance, Grants)."""
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=80, unique=True)
    description = models.CharField(max_length=255, blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name_plural = "Help categories"

    def __str__(self):
        return self.name


class HelpContent(models.Model):
    """
    Single piece of help content: user guide, module help, FAQ, video, or support contact.
    Platform staff publish/unpublish; tenant users see only published items.
    """
    class ContentType(models.TextChoices):
        GUIDE = "guide", "User guide"
        MODULE_HELP = "module_help", "Module help"
        FAQ = "faq", "FAQ"
        VIDEO = "video", "Video tutorial"
        SUPPORT_CONTACT = "support_contact", "Support contact"

    category = models.ForeignKey(
        HelpCategory,
        on_delete=models.PROTECT,
        related_name="contents",
        null=True,
        blank=True,
    )
    content_type = models.CharField(max_length=20, choices=ContentType.choices, db_index=True)
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=120)
    # For FAQ: title = question, body = answer. For video: body = description, video_url used.
    body = models.TextField(blank=True)
    video_url = models.URLField(max_length=500, blank=True, help_text="For video tutorials.")
    # Support contact fields (when content_type = support_contact)
    contact_name = models.CharField(max_length=120, blank=True)
    contact_role = models.CharField(max_length=120, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=60, blank=True)

    is_published = models.BooleanField(default=False, db_index=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "title"]
        unique_together = [["category", "slug"]]
        verbose_name_plural = "Help contents"

    def __str__(self):
        return f"{self.get_content_type_display()}: {self.title}"


class SupportTicket(models.Model):
    """
    Support ticket submitted by a tenant user. Stored at platform level;
    linked to tenant and user for tracking. Platform support staff manage all tickets.
    """
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In progress"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.PROTECT,
        related_name="support_tickets",
    )
    tenant_user_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="ID of the user in the tenant's DB (TenantUser.id).",
    )
    user_email = models.CharField(max_length=254)
    user_name = models.CharField(max_length=255, blank=True)

    subject = models.CharField(max_length=255)
    body = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
        db_index=True,
    )
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.MEDIUM,
    )

    support_notes = models.TextField(blank=True, help_text="Internal notes (not shown to user).")
    support_response = models.TextField(blank=True, help_text="Response to the user.")
    responded_at = models.DateTimeField(null=True, blank=True)
    assigned_to = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_support_tickets",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"#{self.id} {self.subject} ({self.tenant.slug})"
