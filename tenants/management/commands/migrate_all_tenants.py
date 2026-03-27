"""
Run migrations on all tenant databases that have db_name set.
Use after adding new tenants or after creating new migrations for tenant apps.
"""

from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand

from tenants.db import ensure_tenant_db_configured, tenant_db_alias
from tenants.models import Tenant


class Command(BaseCommand):
    help = (
        "Run migrations for every tenant that has a database configured. "
        "Tenant-scoped apps (TENANT_APP_LABELS), including tenant_documents, "
        "only receive schema changes here — not on migrate --database=default."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant",
            default=None,
            help="Optional: run only for this tenant (slug or ID). Default: all tenants.",
        )
        parser.add_argument(
            "--fake-initial",
            action="store_true",
            help="Pass --fake-initial to migrate (useful when DB already matches initial migration).",
        )
        parser.add_argument(
            "--plan",
            action="store_true",
            help="Show migration plan only (does not apply migrations).",
        )

    def handle(self, *args, **options):
        tenant_arg = options.get("tenant")
        if tenant_arg:
            tenants = []
            t = Tenant.objects.filter(slug=tenant_arg).first() or Tenant.objects.filter(pk=tenant_arg).first()
            if t and t.db_name:
                tenants = [t]
            elif not t:
                self.stdout.write(self.style.WARNING(f"Tenant '{tenant_arg}' not found or has no db_name."))
        else:
            tenants = list(Tenant.objects.filter(db_name__isnull=False).exclude(db_name=""))

        if not tenants:
            self.stdout.write("No tenant databases to migrate.")
            return

        kw = {"interactive": False}
        if options.get("fake_initial"):
            kw["fake_initial"] = True
        if options.get("plan"):
            kw["plan"] = True

        for tenant in tenants:
            try:
                ensure_tenant_db_configured(tenant)
                alias = tenant_db_alias(tenant)
                call_command("migrate", database=alias, **kw)
                if options.get("plan"):
                    self.stdout.write(self.style.SUCCESS(f"Plan for tenant '{tenant.slug}' (DB: {alias})."))
                else:
                    self.stdout.write(self.style.SUCCESS(f"Migrated tenant '{tenant.slug}' (DB: {alias})."))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Tenant '{tenant.slug}': {e}"))
