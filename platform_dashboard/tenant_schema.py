"""
Control-plane Tenant table schema introspection (platform console).

Used when production may temporarily lag migrations: avoid SQL referencing
``trial_started_at`` / ``trial_converted_at`` until ``0012_tenant_trial_fields`` is applied.

Clear the cache after migrations in long-lived workers if you need immediate pickup without restart.
"""

from __future__ import annotations

from functools import lru_cache

from django.db import connection

from tenants.models import Tenant


@lru_cache(maxsize=1)
def tenant_table_has_trial_date_columns() -> bool:
    """
    True when the database has both trial date columns on the Tenant table.

    Prefer information_schema on PostgreSQL (reliable); fall back to ORM introspection.
    On any error, return False so platform code avoids referencing missing columns.
    """
    table = Tenant._meta.db_table
    try:
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = %s
                      AND column_name IN ('trial_started_at', 'trial_converted_at')
                    """,
                    [table],
                )
                row = cursor.fetchone()
                return bool(row and row[0] == 2)
        with connection.cursor() as cursor:
            desc = connection.introspection.get_table_description(cursor, table)
        names = {col.name for col in desc}
        return "trial_started_at" in names and "trial_converted_at" in names
    except Exception:
        return False


def clear_tenant_schema_cache() -> None:
    tenant_table_has_trial_date_columns.cache_clear()
