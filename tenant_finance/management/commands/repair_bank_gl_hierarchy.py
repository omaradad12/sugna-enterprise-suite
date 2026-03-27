from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tenants.db import ensure_tenant_db_configured, tenant_db_alias
from tenants.models import Tenant


class Command(BaseCommand):
    help = (
        "Repair BankAccount -> GL links to enforce hierarchy under 1200. "
        "Creates unique child GL accounts (1210, 1220, ...) and relinks invalid/duplicate bank rows."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="Tenant slug or ID.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without saving.",
        )

    def handle(self, *args, **options):
        from tenant_finance.models import BankAccount, ChartAccount

        tenant_arg = options["tenant"]
        dry_run = bool(options.get("dry_run"))

        tenant = Tenant.objects.filter(slug=tenant_arg).first() or Tenant.objects.filter(pk=tenant_arg).first()
        if not tenant:
            raise CommandError("Tenant not found. Use --tenant <slug|id>.")
        if not tenant.db_name:
            raise CommandError("Tenant has no db_name configured.")

        ensure_tenant_db_configured(tenant)
        db = tenant_db_alias(tenant)

        parent = ChartAccount.objects.using(db).filter(code="1200").order_by("id").first()
        if not parent:
            raise CommandError("Missing control account 1200 — Bank Accounts.")

        existing_codes = set(
            ChartAccount.objects.using(db)
            .filter(parent_id=parent.pk)
            .values_list("code", flat=True)
        )

        def next_child_code() -> str:
            if parent.code.isdigit():
                nums = [int(c) for c in existing_codes if (c or "").isdigit()]
                candidate = max([int(parent.code) + 10] + nums) + (0 if not nums else 10)
                if not nums:
                    candidate = int(parent.code) + 10
                rem = candidate % 10
                if rem:
                    candidate += 10 - rem
                while str(candidate) in existing_codes or ChartAccount.objects.using(db).filter(
                    code=str(candidate)
                ).exists():
                    candidate += 10
                return str(candidate)
            base = f"{parent.code}-"
            suffixes = []
            for code in existing_codes:
                if code and code.startswith(base):
                    tail = code[len(base):]
                    if tail.isdigit():
                        suffixes.append(int(tail))
            candidate = (max(suffixes) + 10) if suffixes else 10
            code = f"{base}{candidate:03d}"
            while code in existing_codes or ChartAccount.objects.using(db).filter(code=code).exists():
                candidate += 10
                code = f"{base}{candidate:03d}"
            return code

        def create_child_for_bank(ba: BankAccount):
            code = next_child_code()
            name = f"{ba.bank_name} {ba.currency.code}".strip()[:150]
            existing_codes.add(code)
            if dry_run:
                return None, code, name
            account = ChartAccount.objects.using(db).create(
                code=code,
                name=name,
                type=parent.type,
                statement_type=parent.statement_type or ChartAccount.StatementType.BALANCE_SHEET,
                is_active=True,
                parent_id=parent.pk,
                category_id=parent.category_id,
            )
            return account, code, name

        repaired = 0
        created_accounts = 0
        used_account_ids: set[int] = set()

        bank_accounts = (
            BankAccount.objects.using(db)
            .select_related("account", "currency")
            .order_by("id")
        )

        with transaction.atomic(using=db):
            for ba in bank_accounts:
                acc = ba.account
                valid = bool(acc and acc.code != "1200" and acc.parent_id == parent.pk and acc.is_leaf(db))
                duplicate = bool(acc and acc.pk in used_account_ids)

                if valid and not duplicate:
                    used_account_ids.add(acc.pk)
                    continue

                new_acc, code, name = create_child_for_bank(ba)
                created_accounts += 1
                repaired += 1

                self.stdout.write(
                    f"[{db}] Relink bank #{ba.pk} '{ba.bank_name} / {ba.account_number}' -> {code} {name}"
                )

                if not dry_run and new_acc:
                    BankAccount.objects.using(db).filter(pk=ba.pk).update(account_id=new_acc.pk)
                    used_account_ids.add(new_acc.pk)

            if dry_run:
                transaction.set_rollback(True, using=db)

        mode = "DRY-RUN" if dry_run else "APPLIED"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode}: {repaired} bank accounts relinked, {created_accounts} GL sub-accounts prepared/created in {db}."
            )
        )

