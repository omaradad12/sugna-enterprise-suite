from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from tenants.db import ensure_tenant_db_configured, tenant_db_alias
from tenants.models import Tenant


class Command(BaseCommand):
    help = "Run migrations for a tenant's isolated database."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="Tenant slug or ID.")

    def handle(self, *args, **options):
        tenant_arg = options["tenant"]
        tenant = Tenant.objects.filter(slug=tenant_arg).first() or Tenant.objects.filter(pk=tenant_arg).first()
        if not tenant:
            raise CommandError("Tenant not found. Use --tenant <slug|id>.")
        if not tenant.db_name:
            raise CommandError("Tenant has no db_name configured. Run provision_tenant_db first.")

        ensure_tenant_db_configured(tenant)
        alias = tenant_db_alias(tenant)
        call_command("migrate", database=alias, interactive=False)
        self.stdout.write(self.style.SUCCESS(f"Migrated tenant DB '{alias}'."))  # noqa: T201

