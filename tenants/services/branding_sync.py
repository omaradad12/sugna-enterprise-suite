"""
Copy control-plane TenantBrandingProfile into tenant DB OrganizationSettings for print/PDF paths.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.core.files import File

if TYPE_CHECKING:
    from tenants.models import Tenant

logger = logging.getLogger(__name__)


def sync_tenant_branding_to_organization_settings(tenant: "Tenant", using: str) -> bool:
    """
    Update OrganizationSettings from Tenant + TenantBrandingProfile after provisioning.

    Returns True if a row was written.
    """
    from tenant_finance.models import OrganizationSettings

    profile = getattr(tenant, "branding_profile", None)
    if profile is None:
        try:
            from tenants.models import TenantBrandingProfile

            profile = TenantBrandingProfile.objects.filter(tenant_id=tenant.pk).first()
        except Exception:
            profile = None

    org = OrganizationSettings.objects.using(using).first()
    if not org:
        org = OrganizationSettings.objects.using(using).create()

    name = ""
    if profile and profile.display_full_name:
        name = profile.display_full_name.strip()
    if not name:
        name = tenant.name
    if profile and profile.print_header_organization_name:
        name = profile.print_header_organization_name.strip() or name
    if name:
        org.organization_name = name[:255]

    prim = ""
    sec = ""
    if profile:
        prim = (profile.primary_color or "").strip()
        sec = (profile.secondary_color or "").strip()
    if not prim:
        prim = (getattr(tenant, "brand_primary_color", None) or "").strip()
    if prim:
        org.primary_color = prim[:20]
    if sec:
        org.secondary_color = sec[:20]

    try:

        def _copy_image(field: str, dest_attr: str) -> None:
            if not profile:
                return
            f = getattr(profile, field, None)
            if f and getattr(f, "name", None):
                with f.open("rb") as fh:
                    getattr(org, dest_attr).save(f.name.split("/")[-1], File(fh), save=False)

        if profile:
            if profile.logo:
                _copy_image("logo", "organization_logo")
            if profile.print_header_logo:
                _copy_image("print_header_logo", "report_logo")
            elif profile.logo:
                _copy_image("logo", "report_logo")
    except Exception:
        logger.warning("branding_sync: logo copy failed slug=%s", tenant.slug, exc_info=True)

    org.save(using=using)
    return True
