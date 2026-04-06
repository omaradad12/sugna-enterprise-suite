"""
Post-login landing: launcher vs single-module workspace vs configured default module.
"""

from __future__ import annotations

from django.http import HttpRequest

from rbac.models import user_has_permission
from tenants.services.tenant_modules import tenant_enabled_module_codes
from tenants.workplace import tenant_module_home_relpath


def resolve_post_login_redirect_url(request: HttpRequest) -> str:
    """
    Return absolute path (starting with /) for the tenant workspace after successful login.
    Caller should redirect to /t/<slug>/... using tenant.slug prefix if needed.
    """
    tenant = getattr(request, "tenant", None)
    user = getattr(request, "tenant_user", None)
    tenant_db = getattr(request, "tenant_db", None)
    if not tenant or not user:
        return "/t/"

    slug = tenant.slug
    base = f"/t/{slug}/"

    profile = getattr(tenant, "branding_profile", None)
    if profile is None:
        try:
            from tenants.models import TenantBrandingProfile

            profile = TenantBrandingProfile.objects.filter(tenant_id=tenant.pk).first()
        except Exception:
            profile = None

    mode = (getattr(profile, "post_login_mode", None) or "auto") if profile else "auto"
    if mode == "launcher":
        return base

    codes = tenant_enabled_module_codes(tenant)

    def can_open_module(code: str) -> bool:
        if code == "finance_grants":
            return user_has_permission(user, "module:finance.view", using=tenant_db) or user_has_permission(
                user, "module:grants.view", using=tenant_db
            )
        if code == "hospital":
            return user_has_permission(user, "module:hospital.view", using=tenant_db) or user_has_permission(
                user, "module:hospital.manage", using=tenant_db
            )
        if code == "audit_risk":
            return user_has_permission(user, "module:audit_risk.view", using=tenant_db) or user_has_permission(
                user, "finance:audit.view", using=tenant_db
            )
        if code == "integrations":
            return user_has_permission(user, "module:integrations.manage", using=tenant_db)
        return False

    accessible = [c for c in codes if can_open_module(c)]

    if mode == "default_module" and profile and profile.default_module_code:
        dc = (profile.default_module_code or "").strip()
        if dc in accessible:
            rel = tenant_module_home_relpath(dc)
            if rel:
                return f"{base}{rel}"

    if mode == "auto" and len(accessible) == 1:
        rel = tenant_module_home_relpath(accessible[0])
        if rel:
            return f"{base}{rel}"

    return base
