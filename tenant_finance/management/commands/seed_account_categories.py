"""
Seed standard NGO account categories with statement type for all tenant databases.

Run with:
    python manage.py seed_account_categories
or to target a single DB:
    python manage.py seed_account_categories --database=tenant_1
"""
from django.conf import settings
from django.core.management.base import BaseCommand


STANDARD_CATEGORIES = [
    # name, code, statement_type, display_order, status
    ("Cash", "CASH", "balance_sheet", 10, "active"),
    ("Bank", "BANK", "balance_sheet", 20, "active"),
    ("Receivable", "RECEIVABLE", "balance_sheet", 30, "active"),
    ("Advance", "ADVANCE", "balance_sheet", 40, "active"),
    ("Inventory", "INVENTORY", "balance_sheet", 50, "active"),
    ("Fixed Assets", "FIXED_ASSETS", "balance_sheet", 60, "active"),
    ("Payable", "PAYABLE", "balance_sheet", 70, "active"),
    ("Accrued Liabilities", "ACCRUED_LIAB", "balance_sheet", 80, "active"),
    ("Fund Balance", "FUND_BAL", "balance_sheet", 90, "active"),
    ("Revenue", "REVENUE", "income_expenditure", 110, "active"),
    ("Program Expenses", "PROGRAM_EXP", "income_expenditure", 120, "active"),
    ("Staff Costs", "STAFF_COSTS", "income_expenditure", 130, "active"),
    ("Operating Expenses", "OPER_EXP", "income_expenditure", 140, "active"),
    ("Finance Costs", "FINANCE_COSTS", "income_expenditure", 150, "active"),
]


class Command(BaseCommand):
    help = "Seed standard NGO account categories with statement type for all tenant DBs or --database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            type=str,
            default=None,
            help="Run only for this DB alias (default: all tenant DBs except 'default').",
        )

    def handle(self, *args, **options):
        from tenant_finance.models import AccountCategory

        tenant_apps = set(getattr(settings, "TENANT_APP_LABELS", []))
        if "tenant_finance" not in tenant_apps:
            self.stdout.write("tenant_finance not in TENANT_APP_LABELS, skipping.")
            return

        databases = list(settings.DATABASES.keys())
        if options["database"]:
            db_alias = options["database"]
            if db_alias not in databases:
                self.stderr.write(f"Database '{db_alias}' not found.")
                return
            databases = [db_alias]
        else:
            databases = [db for db in databases if db != "default"]

        total_created = 0
        total_updated = 0

        for db in databases:
            created = 0
            updated = 0
            for name, code, statement_type, display_order, status in STANDARD_CATEGORIES:
                obj, was_created = AccountCategory.objects.using(db).get_or_create(
                    code=code,
                    defaults={
                        "name": name,
                        "statement_type": statement_type,
                        "display_order": display_order,
                        "status": status,
                    },
                )
                if was_created:
                    created += 1
                else:
                    changed = False
                    if obj.name != name:
                        obj.name = name
                        changed = True
                    if (obj.statement_type or "") != (statement_type or ""):
                        obj.statement_type = statement_type
                        changed = True
                    if obj.display_order != display_order:
                        obj.display_order = display_order
                        changed = True
                    if (obj.status or "") != (status or ""):
                        obj.status = status
                        changed = True
                    if changed:
                        obj.save(using=db)
                        updated += 1

            total_created += created
            total_updated += updated
            self.stdout.write(
                self.style.SUCCESS(
                    f"[{db}] Categories seeded: {created} created, {updated} updated."
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Total categories: {total_created} created, {total_updated} updated."
            )
        )

