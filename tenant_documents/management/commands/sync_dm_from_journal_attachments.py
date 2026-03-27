from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from tenants.db import ensure_tenant_db_configured, tenant_db_alias
from tenants.models import Tenant

from tenant_documents.services.sync import sync_all_journal_attachments


class Command(BaseCommand):
    help = "Backfill Document Management records from existing JournalEntryAttachment rows."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="Tenant slug or ID.")

    def handle(self, *args, **options):
        tenant_arg = options["tenant"]
        tenant = Tenant.objects.filter(slug=tenant_arg).first() or Tenant.objects.filter(pk=tenant_arg).first()
        if not tenant:
            raise CommandError("Tenant not found.")
        if not tenant.db_name:
            raise CommandError("Tenant has no db_name configured.")

        ensure_tenant_db_configured(tenant)
        alias = tenant_db_alias(tenant)
        n = sync_all_journal_attachments(alias)
        self.stdout.write(self.style.SUCCESS(f"Synced {n} journal attachment(s) into Document Management (DB '{alias}')."))
