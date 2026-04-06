"""
Merged tenant branding for templates: control-plane profile + tenant DB org settings + legacy Tenant.* fields.
Exposes CSS variables: --tenant-primary, --tenant-secondary, --tenant-accent, --tenant-on-primary, --tenant-on-secondary.
"""

from __future__ import annotations

import re
from typing import Any

from django.http import HttpRequest


_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _parse_hex_rgb(hex_color: str) -> tuple[float, float, float] | None:
    s = (hex_color or "").strip()
    if not s:
        return None
    if not s.startswith("#"):
        s = "#" + s
    if not _HEX_RE.match(s):
        return None
    h = s[1:]
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r = int(h[0:2], 16) / 255.0
        g = int(h[2:4], 16) / 255.0
        b = int(h[4:6], 16) / 255.0
        return (r, g, b)
    except ValueError:
        return None


def _relative_luminance(rgb: tuple[float, float, float]) -> float:
    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def default_text_on_background(hex_bg: str) -> str:
    """Return #ffffff or #111827 for readable contrast on hex_bg."""
    rgb = _parse_hex_rgb(hex_bg)
    if not rgb:
        return "#ffffff"
    lum = _relative_luminance(rgb)
    return "#111827" if lum > 0.55 else "#ffffff"


def build_tenant_theme_context(request: HttpRequest | None) -> dict[str, Any]:
    """
    Returns a dict safe for templates: logo URLs, display names, CSS variable string, print block.
    """
    empty: dict[str, Any] = {
        "tenant_theme": None,
        "tenant_brand_css_vars": "",
        "tenant_print_header": None,
    }
    tenant = getattr(request, "tenant", None) if request else None
    if not tenant:
        return empty

    profile = None
    try:
        profile = getattr(tenant, "branding_profile", None)
    except Exception:
        profile = None
    if profile is None:
        try:
            from tenants.models import TenantBrandingProfile

            profile = TenantBrandingProfile.objects.filter(tenant_id=tenant.pk).first()
        except Exception:
            profile = None

    org_settings = None
    tenant_display = None
    try:
        from tenants.db import ensure_tenant_db_configured, tenant_db_alias
        from tenant_finance.models import OrganizationSettings

        ensure_tenant_db_configured(tenant)
        alias = tenant_db_alias(tenant)
        org_settings = OrganizationSettings.objects.using(alias).first()
        if org_settings and getattr(org_settings, "organization_name", None):
            n = (org_settings.organization_name or "").strip()
            if n:
                tenant_display = n
    except Exception:
        pass

    display_full = ""
    display_short = ""
    if profile:
        display_full = (profile.display_full_name or "").strip()
        display_short = (profile.display_short_name or "").strip()
    if not display_full and org_settings and getattr(org_settings, "organization_name", None):
        display_full = (org_settings.organization_name or "").strip()
    if not display_full:
        display_full = tenant.name
    if not display_short:
        display_short = display_full[:40] if display_full else tenant.slug

    primary = ""
    secondary = ""
    accent = ""
    on_primary = ""
    on_secondary = ""
    if profile:
        primary = (profile.primary_color or "").strip()
        secondary = (profile.secondary_color or "").strip()
        accent = (profile.accent_color or "").strip()
        on_primary = (getattr(profile, "text_on_primary_color", None) or "").strip()
        on_secondary = (getattr(profile, "text_on_secondary_color", None) or "").strip()
    if not primary:
        primary = (getattr(tenant, "brand_primary_color", None) or "").strip()
    if not secondary and org_settings:
        secondary = (getattr(org_settings, "secondary_color", None) or "").strip()
    if not primary:
        primary = "#0078D4"
    if not secondary:
        secondary = "#106ebe"
    if not accent:
        accent = primary
    if not on_primary:
        on_primary = default_text_on_background(primary)
    if not on_secondary:
        on_secondary = default_text_on_background(secondary)

    # Neutral workspace shell (not brand secondary — secondary is for module chrome)
    surface_page = "#faf9f8"

    def _abs_url(url: str | None) -> str | None:
        if not url or not request:
            return url
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return request.build_absolute_uri(url)

    logo_url = None
    favicon_url = None
    login_bg_url = None
    print_logo_url = None

    if profile:
        if getattr(profile, "logo", None) and profile.logo.name:
            logo_url = _abs_url(profile.logo.url)
        if getattr(profile, "favicon", None) and profile.favicon.name:
            favicon_url = _abs_url(profile.favicon.url)
        if getattr(profile, "login_background", None) and profile.login_background.name:
            login_bg_url = _abs_url(profile.login_background.url)
        if getattr(profile, "print_header_logo", None) and profile.print_header_logo.name:
            print_logo_url = _abs_url(profile.print_header_logo.url)

    if not logo_url and org_settings and getattr(org_settings, "organization_logo", None):
        try:
            logo_url = _abs_url(org_settings.organization_logo.url)
        except Exception:
            logo_url = None
    if not logo_url and getattr(tenant, "brand_logo_url", None):
        logo_url = tenant.brand_logo_url

    if not print_logo_url:
        print_logo_url = logo_url
    if org_settings and getattr(org_settings, "report_logo", None) and getattr(org_settings.report_logo, "name", None):
        try:
            print_logo_url = _abs_url(org_settings.report_logo.url)
        except Exception:
            pass

    print_org = (profile.print_header_organization_name if profile else "") or display_full

    # Canonical tokens + legacy aliases used in existing templates
    css_vars = (
        f"--tenant-primary:{primary};"
        f"--tenant-secondary:{secondary};"
        f"--tenant-accent:{accent};"
        f"--tenant-on-primary:{on_primary};"
        f"--tenant-on-secondary:{on_secondary};"
        f"--tenant-brand-primary:{primary};"
        f"--tenant-brand-secondary:{secondary};"
        f"--tenant-brand-accent:{accent};"
        f"--tenant-page-bg:{surface_page};"
        f"--tenant-surface-page:{surface_page};"
    )

    theme = {
        "display_full_name": display_full,
        "display_short_name": display_short,
        "tenant_display_name": tenant_display or display_full,
        "logo_url": logo_url,
        "favicon_url": favicon_url,
        "login_background_url": login_bg_url,
        "primary_color": primary,
        "secondary_color": secondary,
        "accent_color": accent,
        "text_on_primary": on_primary,
        "text_on_secondary": on_secondary,
        "page_background": surface_page,
        "welcome_text": (profile.welcome_text if profile else "") or "",
        "login_subtitle": (getattr(tenant, "brand_login_subtitle", None) or "").strip(),
        "login_title": (getattr(tenant, "brand_login_title", None) or "").strip() or display_full,
        "post_login_mode": (getattr(profile, "post_login_mode", None) or "auto") if profile else "auto",
        "default_module_code": (profile.default_module_code if profile else "") or "",
    }

    print_header = {
        "organization_name": print_org,
        "logo_url": print_logo_url,
        "footer_text": (profile.report_footer_text if profile else "") or "",
        "primary_color": primary,
    }

    return {
        "tenant_theme": theme,
        "tenant_brand_css_vars": css_vars,
        "tenant_print_header": print_header,
    }


def tenant_theme(request: HttpRequest) -> dict[str, Any]:
    """Context processor: merged branding for all tenant portal templates."""
    path = (request.path or "")
    if not path.startswith("/t/") and path != "/t":
        return {"tenant_theme": None, "tenant_brand_css_vars": "", "tenant_print_header": None}
    return build_tenant_theme_context(request)
