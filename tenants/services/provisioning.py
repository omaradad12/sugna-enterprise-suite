from __future__ import annotations

import re
from typing import TYPE_CHECKING

from django.core.management import call_command
from django.db import connection

if TYPE_CHECKING:
    from tenants.models import Tenant

_PG_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")


def validate_pg_identifier(name: str, label: str, *, max_len: int = 63) -> str:
    """PostgreSQL identifier safe for use in quoted DDL (alphanumeric + underscore)."""
    name = (name or "").strip()
    if len(name) > max_len:
        name = name[:max_len].rstrip("_") or "sugna_t"
    if not _PG_IDENT_RE.match(name):
        raise ValueError(f"Invalid {label} '{name}': use only letters, digits, underscore; max {max_len} chars.")
    return name


def provision_postgres_role_and_database(
    *,
    db_name: str,
    db_user: str,
    db_password: str,
) -> None:
    """
    Create role and database on the control-plane connection (superuser / CREATEDB).
    """
    if connection.vendor != "postgresql":
        raise RuntimeError("PostgreSQL required for DB-per-tenant provisioning.")

    db_name = validate_pg_identifier(db_name, "database name")
    db_user = validate_pg_identifier(db_user, "database user")

    with connection.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [db_user])
        if cur.fetchone() is None:
            cur.execute('CREATE USER "{}" WITH PASSWORD %s'.format(db_user), [db_password])

        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", [db_name])
        if cur.fetchone() is None:
            cur.execute('CREATE DATABASE "{}" OWNER "{}"'.format(db_name, db_user))


def drop_postgres_database(db_name: str) -> None:
    """
    Drop a tenant database on the same server as the default Django connection.
    Terminates other backends first. No-op if database does not exist.
    """
    if connection.vendor != "postgresql":
        raise RuntimeError("PostgreSQL required to drop tenant database.")

    db_name = validate_pg_identifier(db_name, "database name")
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = %s
              AND pid <> pg_backend_pid()
            """,
            [db_name],
        )
        cur.execute('DROP DATABASE IF EXISTS "{}"'.format(db_name))


def register_tenant_connection(tenant: Tenant) -> str:
    """Ensure settings.DATABASES has the tenant alias; returns alias."""
    from tenants.db import ensure_tenant_db_configured

    return ensure_tenant_db_configured(tenant)


def run_tenant_migrations(tenant: Tenant) -> None:
    from tenants.db import tenant_db_alias

    register_tenant_connection(tenant)
    alias = tenant_db_alias(tenant)
    call_command("migrate", database=alias, interactive=False)


def run_tenant_initialization(tenant: Tenant) -> dict[str, bool]:
    from tenants.db import tenant_db_alias
    from tenants.services.tenant_init import initialize_tenant_defaults

    register_tenant_connection(tenant)
    alias = tenant_db_alias(tenant)
    return initialize_tenant_defaults(using=alias)


def default_tenant_db_credentials(tenant: Tenant) -> tuple[str, str, str]:
    """Derive default isolated DB name/user and a random password placeholder (caller generates secret)."""
    from secrets import token_urlsafe

    slug = tenant.slug.replace("-", "_")[:40]
    db_name = validate_pg_identifier(f"sugna_{slug}", "database name")
    db_user = validate_pg_identifier(f"sugna_{slug}_user", "database user")
    return db_name, db_user, token_urlsafe(24)
