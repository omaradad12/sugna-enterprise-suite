from __future__ import annotations

from django.db import transaction

from tenants.models import Module, Tenant, TenantModule


@transaction.atomic
def replace_tenant_modules(tenant: Tenant, modules: list[Module] | None) -> None:
    """
    Replace the tenant's module entitlements.

    Required when using an explicit through model (TenantModule), because
    Tenant.modules.set() is not supported with custom through rows.
    """
    TenantModule.objects.filter(tenant=tenant).delete()
    if not modules:
        return
    TenantModule.objects.bulk_create([TenantModule(tenant=tenant, module=m, is_enabled=True) for m in modules])


def tenant_enabled_module_codes(tenant: Tenant) -> set[str]:
    """Module codes that are enabled for this tenant."""
    return set(
        TenantModule.objects.filter(tenant=tenant, is_enabled=True).values_list("module__code", flat=True)
    )
