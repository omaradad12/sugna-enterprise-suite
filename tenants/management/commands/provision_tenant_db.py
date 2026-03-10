from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from tenants.models import Tenant


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

    def handle(self, *args, **options):
        tenant_arg = options["tenant"]
        tenant = Tenant.objects.filter(slug=tenant_arg).first() or Tenant.objects.filter(pk=tenant_arg).first()
        if not tenant:
            raise CommandError("Tenant not found. Use --tenant <slug|id>.")

        tenant.db_name = options["db_name"]
        tenant.db_user = options["db_user"]
        tenant.db_password = options["db_password"]
        tenant.db_host = options["db_host"]
        tenant.db_port = options["db_port"]
        tenant.save(update_fields=["db_name", "db_user", "db_password", "db_host", "db_port"])

        if options["no_create"]:
            self.stdout.write(self.style.SUCCESS("Stored tenant DB credentials (no CREATE USER/DB executed)."))
            return

        if connection.vendor != "postgresql":
            raise CommandError("This command currently supports PostgreSQL only.")

        # Uses the control-plane connection to run provisioning SQL.
        # Requires a DB account with permission to create roles and databases.
        db_name = tenant.db_name
        db_user = tenant.db_user
        db_password = tenant.db_password

        with connection.cursor() as cur:
            # Create role if missing
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [db_user])
            if cur.fetchone() is None:
                cur.execute(f'CREATE USER "{db_user}" WITH PASSWORD %s', [db_password])

            # Create database if missing
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", [db_name])
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{db_name}" OWNER "{db_user}"')

        self.stdout.write(self.style.SUCCESS(f"Provisioned tenant DB '{db_name}' for tenant '{tenant.slug}'."))  # noqa: T201

