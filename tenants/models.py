from django.db import models


class Module(models.Model):
    """
    Represents a high-level platform module (Finance, HR, AI Auditor, etc.).
    """

    code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, help_text="Short description for admins and API consumers.")
    category = models.CharField(
        max_length=50,
        blank=True,
        db_index=True,
        help_text="Logical grouping, e.g. core, platform, governance.",
    )
    sort_order = models.PositiveSmallIntegerField(default=0, help_text="Display order in admin and pickers.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "code"]

    def __str__(self) -> str:
        return self.name


class TenantModule(models.Model):
    """
    Through model for tenant ↔ module entitlements (control plane).

    Use this for per-tenant enablement metadata; query enabled modules via tenant.modules.
    """

    tenant = models.ForeignKey("Tenant", on_delete=models.CASCADE, related_name="tenant_modules")
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="tenant_modules")
    is_enabled = models.BooleanField(default=True, db_index=True)
    enabled_at = models.DateTimeField(auto_now_add=True)
    notes = models.CharField(max_length=255, blank=True, help_text="Internal note (e.g. trial, pilot).")
    limits = models.JSONField(default=dict, blank=True, help_text="Optional JSON limits / feature flags.")

    class Meta:
        ordering = ["module__sort_order", "module__code"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "module"], name="uniq_tenant_module"),
        ]

    def __str__(self) -> str:
        return f"{self.tenant.slug} → {self.module.code}"


class Tenant(models.Model):
    """
    Represents an organization/tenant in the platform.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        TRIAL = "trial", "Trial"
        PENDING = "pending", "Pending"
        SUSPENDED = "suspended", "Suspended"
        EXPIRED = "expired", "Expired"
        FAILED = "failed", "Failed"

    class ProvisioningStatus(models.TextChoices):
        """Lifecycle for automated DB + migrate + init + RBAC onboarding."""

        NOT_STARTED = "not_started", "Not started"
        IN_PROGRESS = "in_progress", "In progress"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

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
    trial_started_at = models.DateField(
        null=True,
        blank=True,
        help_text="When the trial period started (optional; UI falls back to tenant created date).",
    )
    trial_converted_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Set when the tenant converts from trial to a paid subscription.",
    )
    country = models.CharField(max_length=100, blank=True)
    user_count = models.PositiveIntegerField(default=0, help_text="Number of users in this tenant")
    storage_mb = models.PositiveIntegerField(default=0, help_text="Storage used in MB")
    modules = models.ManyToManyField(
        Module,
        through="TenantModule",
        through_fields=("tenant", "module"),
        blank=True,
        related_name="tenants",
        help_text="Enabled modules for this tenant (use TenantModule for metadata).",
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

    # Automated onboarding (DB create → migrate → defaults → RBAC).
    provisioning_status = models.CharField(
        max_length=20,
        choices=ProvisioningStatus.choices,
        default=ProvisioningStatus.NOT_STARTED,
        db_index=True,
        help_text="Tracks automatic provisioning pipeline; inspect provisioning_error if failed.",
    )
    provisioning_error = models.TextField(
        blank=True,
        help_text="Last provisioning failure message (cleared on success).",
    )
    provisioned_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When provisioning_status last reached success.",
    )

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
        if self.status in (self.Status.FAILED, self.Status.DRAFT):
            return self.status
        if not self.is_active:
            return self.Status.SUSPENDED if self.status == self.Status.ACTIVE else self.status
        return self.status


class SubscriptionPlan(models.Model):
    """
    Named subscription / pricing tier in the control plane (reference data).

    Tenant.plan is a free-text field today; you can align it with SubscriptionPlan.code in UI or future FK.
    """

    class BillingCycle(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Quarterly"
        YEARLY = "yearly", "Yearly"
        ONE_TIME = "one_time", "One-time"

    class Visibility(models.TextChoices):
        PUBLIC = "public", "Public"
        INTERNAL = "internal", "Internal"

    code = models.SlugField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    is_draft = models.BooleanField(default=False, db_index=True)
    is_archived = models.BooleanField(default=False, db_index=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="USD")
    billing_cycle = models.CharField(
        max_length=20,
        choices=BillingCycle.choices,
        default=BillingCycle.MONTHLY,
    )
    trial_enabled = models.BooleanField(default=False)
    trial_duration_days = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Trial length in days when trial is enabled.",
    )

    visibility = models.CharField(
        max_length=20,
        choices=Visibility.choices,
        default=Visibility.PUBLIC,
        db_index=True,
    )

    max_users = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Leave empty for unlimited.",
    )
    max_storage_mb = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Leave empty for unlimited.",
    )
    max_organizations = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Included tenant organizations (optional cap).",
    )

    included_modules = models.ManyToManyField(
        "Module",
        blank=True,
        related_name="subscription_plans",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "code"]

    def __str__(self) -> str:
        return self.name

    def is_catalog_assignable(self) -> bool:
        """Shown in pickers when the plan can be sold or assigned."""
        return bool(self.is_active and not self.is_draft and not self.is_archived)


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


class TenantBrandingProfile(models.Model):
    """
    Visual identity and default workplace behavior (control plane).

    Synced into tenant DB OrganizationSettings during provisioning for print/report paths.
    """

    class PostLoginMode(models.TextChoices):
        AUTO = "auto", "Auto (single module → workspace; else launcher)"
        LAUNCHER = "launcher", "Always show module launcher"
        DEFAULT_MODULE = "default_module", "Open default module workspace"

    tenant = models.OneToOneField(
        Tenant,
        on_delete=models.CASCADE,
        related_name="branding_profile",
    )

    display_full_name = models.CharField(max_length=255, blank=True)
    display_short_name = models.CharField(max_length=120, blank=True)

    logo = models.ImageField(upload_to="tenant_branding/logos/%Y/%m/", blank=True, max_length=255)
    favicon = models.FileField(upload_to="tenant_branding/favicons/%Y/%m/", blank=True, max_length=255)
    login_background = models.ImageField(
        upload_to="tenant_branding/login_bg/%Y/%m/", blank=True, max_length=255
    )

    primary_color = models.CharField(max_length=20, blank=True)
    secondary_color = models.CharField(max_length=20, blank=True)
    accent_color = models.CharField(max_length=20, blank=True)
    text_on_primary_color = models.CharField(
        max_length=20,
        blank=True,
        help_text="Foreground on primary (top header). Auto if blank.",
    )
    text_on_secondary_color = models.CharField(
        max_length=20,
        blank=True,
        help_text="Foreground on secondary (module nav bar). Auto if blank.",
    )

    print_header_logo = models.ImageField(upload_to="tenant_branding/print/%Y/%m/", blank=True, max_length=255)
    print_header_organization_name = models.CharField(max_length=255, blank=True)
    report_footer_text = models.CharField(max_length=500, blank=True)

    welcome_text = models.TextField(blank=True)

    post_login_mode = models.CharField(
        max_length=32,
        choices=PostLoginMode.choices,
        default=PostLoginMode.AUTO,
    )
    default_module_code = models.CharField(max_length=80, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tenant branding profile"
        verbose_name_plural = "Tenant branding profiles"

    def __str__(self) -> str:
        return f"Branding: {self.tenant.slug}"

