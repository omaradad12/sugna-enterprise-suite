"""
CLI entry point for the same onboarding pipeline used by the platform tenant registration UI.

Example:
  python manage.py provision_tenant_onboard --tenant hurdo \\
    --admin-email admin@hurdo.org --admin-password 'SecurePass123'
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from tenants.models import Tenant
from tenants.services.onboarding import run_full_tenant_provisioning


class Command(BaseCommand):
    help = "Full onboarding: create DB/user (unless skipped), save credentials, migrate, defaults, RBAC."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="Tenant slug or ID.")
        parser.add_argument("--db-name", default="", help="Override database name (default: derived from slug).")
        parser.add_argument("--db-user", default="", help="Override database user.")
        parser.add_argument("--db-password", default="", help="Override database password.")
        parser.add_argument("--db-host", default="", help="Database host override.")
        parser.add_argument("--db-port", default="", help="Database port override.")
        parser.add_argument(
            "--skip-create-db",
            action="store_true",
            help="Do not run CREATE USER/DATABASE (store credentials only).",
        )
        parser.add_argument("--admin-email", default="", help="Tenant admin email (optional; skips RBAC if empty).")
        parser.add_argument("--admin-password", default="", help="Tenant admin password (optional; auto-generated if empty).")
        parser.add_argument("--admin-full-name", default="Tenant Admin", help="Admin display name.")

    def handle(self, *args, **options):
        tenant_arg = options["tenant"]
        tenant = Tenant.objects.filter(slug=tenant_arg).first() or Tenant.objects.filter(pk=tenant_arg).first()
        if not tenant:
            raise CommandError("Tenant not found.")

        result = run_full_tenant_provisioning(
            tenant,
            db_name=options["db_name"] or None,
            db_user=options["db_user"] or None,
            db_password=options["db_password"] or None,
            db_host=options["db_host"] or "",
            db_port=options["db_port"] or "",
            skip_create_db=options["skip_create_db"],
            admin_email=options["admin_email"] or None,
            admin_password=options["admin_password"] or None,
            admin_full_name=options["admin_full_name"],
        )
        if result.ok:
            self.stdout.write(self.style.SUCCESS(result.message))
            if result.generated_admin_password:
                self.stdout.write(
                    self.style.WARNING(
                        "Generated tenant admin password (copy now): " f"{result.generated_admin_password}"
                    )
                )
        else:
            raise CommandError(result.message)
