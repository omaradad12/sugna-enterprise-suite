from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from sugna_core.tenant_context import set_current_tenant
from tenants.db import ensure_tenant_db_configured, tenant_db_alias
from tenants.models import Tenant


class Command(BaseCommand):
    help = (
        "Run migrations for a tenant's isolated database. "
        "Use this for tenant_documents and other TENANT_APP_LABELS apps."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="Tenant slug or ID.")
        parser.add_argument(
            "--fake-initial",
            action="store_true",
            help="Pass --fake-initial to migrate (DB already matches initial migration).",
        )
        parser.add_argument(
            "--plan",
            action="store_true",
            help="Show migration plan only.",
        )

    def handle(self, *args, **options):
        tenant_arg = options["tenant"]
        tenant = Tenant.objects.filter(slug=tenant_arg).first() or Tenant.objects.filter(pk=tenant_arg).first()
        if not tenant:
            raise CommandError("Tenant not found. Use --tenant <slug|id>.")
        if not tenant.db_name:
            raise CommandError("Tenant has no db_name configured. Run provision_tenant_db first.")

        ensure_tenant_db_configured(tenant)
        alias = tenant_db_alias(tenant)
        kw: dict = {"database": alias, "interactive": False}
        if options.get("fake_initial"):
            kw["fake_initial"] = True
        if options.get("plan"):
            kw["plan"] = True
        try:
            set_current_tenant(tenant)
            call_command("migrate", **kw)
        finally:
            set_current_tenant(None)
        self.stdout.write(self.style.SUCCESS(f"Migrated tenant DB '{alias}'."))  # noqa: T201

