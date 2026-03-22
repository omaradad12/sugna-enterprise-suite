"""
End-to-end tenant onboarding: PostgreSQL DB + credentials on Tenant row + migrate + defaults + RBAC.

Order of operations avoids a broken control-plane row:
1. Create role/database on the server (idempotent) *before* persisting secrets if possible.
2. Persist db_* on Tenant only after DDL succeeds (or when using --no-create with pre-existing DB).
3. Migrate → tenant defaults → optional bootstrap_tenant_rbac.
4. Mark ACTIVE only when the requested steps succeed.

Safe to re-run: DDL and migrations are idempotent; RBAC bootstrap uses get_or_create patterns.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from tenants.models import Tenant
from tenants.services.provisioning import (
    default_tenant_db_credentials,
    provision_postgres_role_and_database,
    run_tenant_initialization,
    run_tenant_migrations,
    validate_pg_identifier,
)

logger = logging.getLogger(__name__)


@dataclass
class TenantOnboardingResult:
    ok: bool
    message: str
    step: str | None = None
    """One-time generated tenant-admin password (only when auto-generated). Never stored on Tenant."""

    generated_admin_password: str | None = None


def _fail(tenant: Tenant, step: str, exc: BaseException, *, persist_on_tenant: bool = True) -> TenantOnboardingResult:
    err = f"{step}: {exc}"
    logger.error("Tenant onboarding failed slug=%s: %s", tenant.slug, err, exc_info=True)
    if persist_on_tenant:
        tenant.provisioning_status = tenant.ProvisioningStatus.FAILED
        tenant.provisioning_error = err[:4000]
        tenant.is_active = False
        tenant.status = tenant.Status.FAILED
        tenant.save(
            update_fields=[
                "provisioning_status",
                "provisioning_error",
                "is_active",
                "status",
                "updated_at",
            ]
        )
    return TenantOnboardingResult(ok=False, message=err, step=step)


def _succeed(
    tenant: Tenant,
    *,
    message: str,
    generated_admin_password: str | None = None,
) -> TenantOnboardingResult:
    tenant.provisioning_status = tenant.ProvisioningStatus.SUCCESS
    tenant.provisioning_error = ""
    tenant.provisioned_at = timezone.now()
    tenant.is_active = True
    tenant.status = tenant.Status.ACTIVE
    tenant.save(
        update_fields=[
            "provisioning_status",
            "provisioning_error",
            "provisioned_at",
            "is_active",
            "status",
            "updated_at",
        ]
    )
    logger.info("Tenant onboarding success slug=%s", tenant.slug)
    return TenantOnboardingResult(
        ok=True,
        message=message,
        generated_admin_password=generated_admin_password,
    )


def run_full_tenant_provisioning(
    tenant: Tenant,
    *,
    db_name: str | None = None,
    db_user: str | None = None,
    db_password: str | None = None,
    db_host: str = "",
    db_port: str = "",
    skip_create_db: bool = False,
    admin_email: str | None = None,
    admin_password: str | None = None,
    admin_full_name: str | None = None,
    auto_generate_admin_password: bool = True,
    reuse_saved_credentials: bool = False,
    register_flow: bool = False,
) -> TenantOnboardingResult:
    """
    Run the full onboarding pipeline for an existing Tenant row.

    :param reuse_saved_credentials: If True and Tenant already has db_* set, skip credential generation
        and DDL (assumes DB already exists). Useful for retry after a late failure.
    :param skip_create_db: If True, only persist credentials (manual DBA setup); no CREATE USER/DATABASE.
    :param register_flow: If True, failures do not persist FAILED state on the Tenant row (caller may
        delete the row and drop the database instead).
    """
    persist_fail = not register_flow
    tenant.provisioning_status = Tenant.ProvisioningStatus.IN_PROGRESS
    tenant.provisioning_error = ""
    tenant.save(update_fields=["provisioning_status", "provisioning_error", "updated_at"])

    gen_pw: str | None = None

    try:
        # --- Credentials ---
        if reuse_saved_credentials and tenant.db_name and tenant.db_user and tenant.db_password:
            db_name = tenant.db_name
            db_user = tenant.db_user
            db_password = tenant.db_password
        else:
            if not db_name or not db_user or not db_password:
                auto_name, auto_user, auto_pw = default_tenant_db_credentials(tenant)
                db_name = db_name or auto_name
                db_user = db_user or auto_user
                db_password = db_password or auto_pw
            validate_pg_identifier(db_name, "database name")
            validate_pg_identifier(db_user, "database user")

        # --- DDL first (no secrets on row yet if this is a fresh provision) ---
        if not skip_create_db:
            try:
                provision_postgres_role_and_database(
                    db_name=db_name,
                    db_user=db_user,
                    db_password=db_password,
                )
            except Exception as exc:
                return _fail(tenant, "create_database_or_role", exc, persist_on_tenant=persist_fail)
        else:
            logger.info("Skipping PostgreSQL DDL for tenant slug=%s (--no-create style)", tenant.slug)

        # --- Persist connection metadata on control-plane row ---
        with transaction.atomic():
            tenant.db_name = db_name
            tenant.db_user = db_user
            tenant.db_password = db_password
            tenant.db_host = db_host or tenant.db_host
            tenant.db_port = db_port or tenant.db_port
            tenant.save(
                update_fields=[
                    "db_name",
                    "db_user",
                    "db_password",
                    "db_host",
                    "db_port",
                    "updated_at",
                ]
            )

        # --- Migrations on tenant alias ---
        try:
            run_tenant_migrations(tenant)
        except Exception as exc:
            return _fail(tenant, "migrate_tenant", exc, persist_on_tenant=persist_fail)

        # --- Default rows (currencies, FY, COA scaffold, etc.) ---
        try:
            init_summary = run_tenant_initialization(tenant)
            logger.info("Tenant init summary slug=%s: %s", tenant.slug, init_summary)
        except Exception as exc:
            return _fail(tenant, "initialize_tenant_defaults", exc, persist_on_tenant=persist_fail)

        # --- RBAC + tenant admin (optional) ---
        email = (admin_email or "").strip().lower()
        if email:
            pw = (admin_password or "").strip()
            if not pw:
                if not auto_generate_admin_password:
                    return _fail(
                        tenant,
                        "bootstrap_rbac",
                        ValueError("admin_password is required when auto_generate_admin_password is False."),
                        persist_on_tenant=persist_fail,
                    )
                from secrets import token_urlsafe

                pw = token_urlsafe(18)
                gen_pw = pw
            full_name = (admin_full_name or "").strip() or "Tenant Admin"
            try:
                call_command(
                    "bootstrap_tenant_rbac",
                    tenant=tenant.slug,
                    email=email,
                    password=pw,
                    full_name=full_name,
                )
            except Exception as exc:
                return _fail(tenant, "bootstrap_tenant_rbac", exc, persist_on_tenant=persist_fail)
        else:
            logger.info("Skipping RBAC bootstrap (no admin_email) for tenant slug=%s", tenant.slug)

        msg = f"Tenant «{tenant.slug}» provisioned (database={db_name})."
        if email and gen_pw:
            msg += f" Initial admin: {email} — temporary password was auto-generated (share securely)."
        return _succeed(tenant, message=msg, generated_admin_password=gen_pw)

    except Exception as exc:
        return _fail(tenant, "unexpected", exc, persist_on_tenant=persist_fail)
