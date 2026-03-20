"""
Re-run onboarding for a tenant after a failure, or complete steps for a partially configured tenant.

If the tenant row already has db_* credentials, uses reuse_saved_credentials=True (DDL is still
idempotent if you omit skip). If provisioning never stored credentials, runs a full fresh flow.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from tenants.models import Tenant
from tenants.services.onboarding import run_full_tenant_provisioning


class Command(BaseCommand):
    help = "Retry full tenant provisioning (migrate, defaults, RBAC) for slug or ID."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="Tenant slug or ID.")
        parser.add_argument(
            "--skip-create-db",
            action="store_true",
            help="Do not run CREATE USER/DATABASE (credentials must already exist on server).",
        )
        parser.add_argument("--admin-email", default="", help="Tenant admin email for RBAC bootstrap.")
        parser.add_argument("--admin-password", default="", help="Tenant admin password (optional if auto-generate).")
        parser.add_argument("--admin-full-name", default="Tenant Admin", help="Display name for admin user.")

    def handle(self, *args, **options):
        tenant_arg = options["tenant"]
        tenant = Tenant.objects.filter(slug=tenant_arg).first() or Tenant.objects.filter(pk=tenant_arg).first()
        if not tenant:
            raise CommandError("Tenant not found.")

        reuse = bool(tenant.db_name and tenant.db_user and tenant.db_password)
        result = run_full_tenant_provisioning(
            tenant,
            skip_create_db=options["skip_create_db"],
            admin_email=options["admin_email"] or None,
            admin_password=options["admin_password"] or None,
            admin_full_name=options["admin_full_name"],
            reuse_saved_credentials=reuse,
        )
        if result.ok:
            self.stdout.write(self.style.SUCCESS(result.message))
            if result.generated_admin_password:
                self.stdout.write(
                    self.style.WARNING(
                        "Generated tenant admin password (copy now; not stored): "
                        f"{result.generated_admin_password}"
                    )
                )
        else:
            raise CommandError(result.message)
