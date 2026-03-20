from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from tenants.models import Tenant
from tenants.services.provisioning import (
    provision_postgres_role_and_database,
    run_tenant_initialization,
    run_tenant_migrations,
    validate_pg_identifier,
)


class Command(BaseCommand):
    help = "Provision an isolated Postgres database for a tenant (DB-per-tenant)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="Tenant slug or ID.")
        parser.add_argument("--db-name", required=True, help="Tenant database name.")
        parser.add_argument("--db-user", required=True, help="Tenant database user.")
        parser.add_argument("--db-password", required=True, help="Tenant database password.")
        parser.add_argument("--db-host", default="", help="Tenant database host (defaults to control plane host).")
        parser.add_argument("--db-port", default="", help="Tenant database port (defaults to control plane port).")
        parser.add_argument(
            "--no-create",
            action="store_true",
            help="Only store credentials on the Tenant record; do not run CREATE USER/DB SQL.",
        )
        parser.add_argument(
            "--migrate",
            action="store_true",
            help="After provisioning, run migrate for this tenant's database.",
        )
        parser.add_argument(
            "--init-defaults",
            action="store_true",
            help="After migrate (or if DB already exists), seed default tenant data (currencies, org settings).",
        )

    def handle(self, *args, **options):
        tenant_arg = options["tenant"]
        tenant = Tenant.objects.filter(slug=tenant_arg).first() or Tenant.objects.filter(pk=tenant_arg).first()
        if not tenant:
            raise CommandError("Tenant not found. Use --tenant <slug|id>.")

        # Validate identifiers early (avoids SQL injection / invalid DDL)
        try:
            validate_pg_identifier(options["db_name"], "database name")
            validate_pg_identifier(options["db_user"], "database user")
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        tenant.db_name = options["db_name"]
        tenant.db_user = options["db_user"]
        tenant.db_password = options["db_password"]
        tenant.db_host = options["db_host"]
        tenant.db_port = options["db_port"]
        tenant.save(update_fields=["db_name", "db_user", "db_password", "db_host", "db_port"])

        if options["no_create"]:
            self.stdout.write(self.style.SUCCESS("Stored tenant DB credentials (no CREATE USER/DB executed)."))
        else:
            if connection.vendor != "postgresql":
                raise CommandError("This command currently supports PostgreSQL only.")
            try:
                provision_postgres_role_and_database(
                    db_name=tenant.db_name,
                    db_user=tenant.db_user,
                    db_password=tenant.db_password,
                )
            except ValueError as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(
                self.style.SUCCESS(f"Provisioned tenant DB '{tenant.db_name}' for tenant '{tenant.slug}'.")
            )

        if options["migrate"]:
            try:
                run_tenant_migrations(tenant)
                self.stdout.write(self.style.SUCCESS(f"Migrations applied for tenant '{tenant.slug}'."))
            except Exception as exc:
                raise CommandError(f"Migrate failed: {exc}") from exc

        if options["init_defaults"]:
            if not tenant.db_name:
                raise CommandError("Tenant has no db_name; cannot initialize defaults.")
            try:
                summary = run_tenant_initialization(tenant)
                self.stdout.write(self.style.SUCCESS(f"Default tenant initialization: {summary}"))
            except Exception as exc:
                raise CommandError(f"Initialization failed: {exc}") from exc
