from django.db import models


class Permission(models.Model):
    """
    Tenant-scoped permissions. Use a stable code string like:
      - module:billing.view
      - module:billing.manage
      - record:ai_auditor.finding.read
    """

    code = models.CharField(max_length=150, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code


class Role(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class RolePermission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name="permission_roles")

    class Meta:
        unique_together = ("role", "permission")

    def __str__(self) -> str:
        return f"{self.role} → {self.permission}"


class UserRole(models.Model):
    user = models.ForeignKey("tenant_users.TenantUser", on_delete=models.CASCADE, related_name="user_roles")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_users")

    class Meta:
        unique_together = ("user", "role")

    def __str__(self) -> str:
        return f"{self.user} → {self.role}"


def user_has_permission(user, code: str, using: str) -> bool:
    """
    Check if a tenant user has a permission code in the tenant DB.
    """
    if getattr(user, "is_tenant_admin", False):
        return True
    return RolePermission.objects.using(using).filter(
        role__role_users__user_id=user.id,
        permission__code=code,
    ).exists()
