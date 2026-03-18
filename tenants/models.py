from django.db import models


class Module(models.Model):
    """
    Represents a high-level platform module (Finance, HR, AI Auditor, etc.).
    """

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return self.name


class Tenant(models.Model):
    """
    Represents an organization/tenant in the platform.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        TRIAL = "trial", "Trial"
        PENDING = "pending", "Pending"
        SUSPENDED = "suspended", "Suspended"
        EXPIRED = "expired", "Expired"

    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    domain = models.CharField(
        max_length=255,
        unique=True,
        help_text="Domain or subdomain used to route this tenant, e.g. ngo1.sugna.org (no protocol or path).",
    )
    is_active = models.BooleanField(default=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        help_text="Display status for tenant lifecycle (Active, Trial, Pending, Suspended, Expired)",
    )
    plan = models.CharField(max_length=100, blank=True, help_text="Subscription plan name")
    subscription_expiry = models.DateField(null=True, blank=True)
    country = models.CharField(max_length=100, blank=True)
    user_count = models.PositiveIntegerField(default=0, help_text="Number of users in this tenant")
    storage_mb = models.PositiveIntegerField(default=0, help_text="Storage used in MB")
    modules = models.ManyToManyField(
        Module,
        blank=True,
        related_name="tenants",
        help_text="Enabled modules for this tenant",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Per-tenant database connection (DB-per-tenant architecture).
    # These fields belong to the control plane and should never store tenant business data.
    db_name = models.CharField(max_length=128, blank=True, help_text="Database name for this tenant (isolated DB).")
    db_user = models.CharField(max_length=128, blank=True, help_text="Database user for this tenant (least privilege).")
    db_password = models.CharField(max_length=256, blank=True, help_text="Database password for this tenant.")
    db_host = models.CharField(max_length=255, blank=True, help_text="Database host for this tenant.")
    db_port = models.CharField(max_length=10, blank=True, help_text="Database port for this tenant.")

    # Optional branding for tenant-facing experiences (e.g., login page).
    brand_logo_url = models.URLField(blank=True, help_text="Public URL of the tenant logo for login screens.")
    brand_primary_color = models.CharField(
        max_length=20,
        blank=True,
        help_text="Primary brand color (hex) used on buttons and accents.",
    )
    brand_background_color = models.CharField(
        max_length=20,
        blank=True,
        help_text="Background color (hex) for tenant login window.",
    )
    brand_login_title = models.CharField(
        max_length=120,
        blank=True,
        help_text="Custom title on login page (defaults to 'Sign in').",
    )
    brand_login_subtitle = models.CharField(
        max_length=255,
        blank=True,
        help_text="Custom subtitle on login page beneath the title.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def display_status(self):
        """Status for display; respects is_active for Active/Suspended."""
        if not self.is_active:
            return self.Status.SUSPENDED if self.status == self.Status.ACTIVE else self.status
        return self.status


class TenantDomain(models.Model):
    """
    Maps one or more domains/subdomains to a tenant (control plane).
    Supports custom domains and multiple hostnames per tenant.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="domains")
    domain = models.CharField(max_length=255, unique=True)
    is_primary = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["domain"]

    def __str__(self) -> str:
        return self.domain

