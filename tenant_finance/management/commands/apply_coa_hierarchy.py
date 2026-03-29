from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tenants.db import ensure_tenant_db_configured, tenant_db_alias
from tenants.models import Tenant


class Command(BaseCommand):
    help = (
        "Apply parent-child hierarchy for Chart of Accounts by code structure. "
        "Examples: 1100->1000, 1210->1200, 5110->5100."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="Tenant slug or ID.")
        parser.add_argument("--dry-run", action="store_true", help="Preview without saving.")

    def handle(self, *args, **options):
        from tenant_finance.models import ChartAccount, normalize_finance_account_class

        tenant_arg = options["tenant"]
        dry_run = bool(options.get("dry_run"))

        tenant = Tenant.objects.filter(slug=tenant_arg).first() or Tenant.objects.filter(pk=tenant_arg).first()
        if not tenant:
            raise CommandError("Tenant not found. Use --tenant <slug|id>.")
        if not tenant.db_name:
            raise CommandError("Tenant has no db_name configured.")

        ensure_tenant_db_configured(tenant)
        db = tenant_db_alias(tenant)

        accounts = list(ChartAccount.objects.using(db).order_by("code", "id"))
        by_code: dict[str, ChartAccount] = {}
        for a in accounts:
            by_code.setdefault((a.code or "").strip(), a)

        updates = 0
        with transaction.atomic(using=db):
            for a in accounts:
                code = (a.code or "").strip()
                if not code.isdigit() or len(code) < 4:
                    continue

                parent_code = ""
                if code.endswith("00"):
                    parent_code = f"{code[0]}000"
                elif code.endswith("0"):
                    parent_code = f"{code[:-2]}00"

                if not parent_code or parent_code == code:
                    continue
                parent = by_code.get(parent_code)
                if not parent:
                    continue
                if a.parent_id == parent.pk:
                    continue
                if normalize_finance_account_class(a.type) != normalize_finance_account_class(parent.type):
                    continue

                self.stdout.write(f"[{db}] {a.code} {a.name} -> parent {parent.code} {parent.name}")
                updates += 1
                if not dry_run:
                    ChartAccount.objects.using(db).filter(pk=a.pk).update(parent_id=parent.pk)

            if dry_run:
                transaction.set_rollback(True, using=db)

        mode = "DRY-RUN" if dry_run else "APPLIED"
        self.stdout.write(self.style.SUCCESS(f"{mode}: {updates} account hierarchy links updated in {db}."))

