"""
Rollback helpers when platform tenant registration provisioning fails mid-flight.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import connections

if TYPE_CHECKING:
    from tenants.models import Tenant

logger = logging.getLogger(__name__)


def cleanup_failed_registration_tenant(tenant: Tenant) -> None:
    """
    Close dynamic DB alias, drop isolated PostgreSQL database if it was created,
    then delete the control-plane Tenant row (and related TenantDomain rows).
    """
    from tenants.db import tenant_db_alias
    from tenants.models import Tenant
    from tenants.services.provisioning import drop_postgres_database

    pk = tenant.pk
    db_name = (tenant.db_name or "").strip()
    alias = tenant_db_alias(tenant)

    if alias in settings.DATABASES:
        try:
            connections[alias].close()
        except Exception:
            logger.debug("Could not close connection alias %s", alias, exc_info=True)
        try:
            del settings.DATABASES[alias]
        except Exception:
            logger.debug("Could not remove settings.DATABASES[%s]", alias, exc_info=True)

    if db_name:
        try:
            drop_postgres_database(db_name)
        except Exception:
            logger.exception(
                "Could not drop tenant database %s; it may require manual cleanup.",
                db_name,
            )

    deleted, _ = Tenant.objects.filter(pk=pk).delete()
    if not deleted:
        logger.warning("cleanup_failed_registration_tenant: tenant pk=%s already removed", pk)
