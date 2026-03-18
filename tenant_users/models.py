from django.db import models
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone


class TenantUser(models.Model):
    """
    Tenant-scoped user record stored inside the tenant database.

    This is intentionally separate from Django's global auth user so tenants remain fully isolated.
    """

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    is_tenant_admin = models.BooleanField(default=False)
    password_hash = models.CharField(max_length=256, blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Profile (My Profile page)
    phone_number = models.CharField(max_length=30, blank=True)
    position = models.CharField(max_length=120, blank=True, help_text="Job title")
    department = models.CharField(max_length=120, blank=True)
    profile_photo = models.ImageField(upload_to="tenant_profiles/%Y/%m/", null=True, blank=True, max_length=255)
    preferred_language = models.CharField(max_length=10, blank=True, default="en")
    time_zone = models.CharField(max_length=50, blank=True, default="UTC")

    # Notification preferences
    email_notifications = models.BooleanField(default=True)
    system_alerts = models.BooleanField(default=True)
    approval_notifications = models.BooleanField(default=True)

    # 2FA (optional TOTP)
    two_factor_enabled = models.BooleanField(default=False)
    totp_secret = models.CharField(max_length=32, blank=True, help_text="Base32 TOTP secret for authenticator apps.")

    # Assigned projects (grants) for User Management
    assigned_grants = models.ManyToManyField(
        "tenant_grants.Grant",
        blank=True,
        related_name="assigned_users",
        help_text="Grants/projects this user is assigned to.",
    )

    class Meta:
        ordering = ["email"]

    def __str__(self) -> str:
        return self.email

    def get_full_name(self) -> str:
        name = (self.full_name or "").strip()
        return name or (self.email or "")

    def get_short_name(self) -> str:
        name = (self.full_name or "").strip()
        if name:
            return name.split()[0]
        return (self.email or "")

    def set_password(self, raw_password: str) -> None:
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        if not self.password_hash:
            return False
        return check_password(raw_password, self.password_hash)

    def touch_login(self) -> None:
        self.last_login_at = timezone.now()
        self.save(update_fields=["last_login_at"])


class TenantLoginLog(models.Model):
    """Log of tenant user logins for Login Activity History on My Profile."""
    user = models.ForeignKey(TenantUser, on_delete=models.CASCADE, related_name="login_logs")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "-created_at"])]
