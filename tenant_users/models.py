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

    class Meta:
        ordering = ["email"]

    def __str__(self) -> str:
        return self.email

    def set_password(self, raw_password: str) -> None:
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        if not self.password_hash:
            return False
        return check_password(raw_password, self.password_hash)

    def touch_login(self) -> None:
        self.last_login_at = timezone.now()
        self.save(update_fields=["last_login_at"])
