"""
Seed standard NGO account categories with statement type for all tenant databases.

Run with:
    python manage.py seed_account_categories
or to target a single DB:
    python manage.py seed_account_categories --database=tenant_1
"""
from django.conf import settings
from django.core.management.base import BaseCommand


# Top-level NGO system categories (enterprise standard)
SYSTEM_ROOT_CATEGORIES = [
    # name, code, statement_type, category_type, normal_balance, display_order, status
    ("Assets", "ASSETS", "balance_sheet", "asset", "debit", 5, "active"),
    ("Liabilities", "LIABILITIES", "balance_sheet", "liability", "credit", 6, "active"),
    ("Equity", "EQUITY", "balance_sheet", "equity", "credit", 7, "active"),
    ("Income", "INCOME", "income_expenditure", "income", "credit", 8, "active"),
    ("Expenses", "EXPENSES", "income_expenditure", "expense", "debit", 9, "active"),
]

# Detailed categories: name, code, statement_type, display_order, status, category_type, normal_balance, parent_code
STANDARD_CATEGORIES = [
    ("Cash", "CASH", "balance_sheet", 10, "active", "asset", "debit", "ASSETS"),
    ("Bank", "BANK", "balance_sheet", 20, "active", "asset", "debit", "ASSETS"),
    ("Receivable", "RECEIVABLE", "balance_sheet", 30, "active", "asset", "debit", "ASSETS"),
    ("Advance", "ADVANCE", "balance_sheet", 40, "active", "asset", "debit", "ASSETS"),
    ("Inventory", "INVENTORY", "balance_sheet", 50, "active", "asset", "debit", "ASSETS"),
    ("Fixed Assets", "FIXED_ASSETS", "balance_sheet", 60, "active", "asset", "debit", "ASSETS"),
    ("Payable", "PAYABLE", "balance_sheet", 70, "active", "liability", "credit", "LIABILITIES"),
    ("Accrued Liabilities", "ACCRUED_LIAB", "balance_sheet", 80, "active", "liability", "credit", "LIABILITIES"),
    ("Fund Balance", "FUND_BAL", "balance_sheet", 90, "active", "equity", "credit", "EQUITY"),
    ("Revenue", "REVENUE", "income_expenditure", 110, "active", "income", "credit", "INCOME"),
    ("Program Expenses", "PROGRAM_EXP", "income_expenditure", 120, "active", "expense", "debit", "EXPENSES"),
    ("Staff Costs", "STAFF_COSTS", "income_expenditure", 130, "active", "expense", "debit", "EXPENSES"),
    ("Operating Expenses", "OPER_EXP", "income_expenditure", 140, "active", "expense", "debit", "EXPENSES"),
    ("Finance Costs", "FINANCE_COSTS", "income_expenditure", 150, "active", "expense", "debit", "EXPENSES"),
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
            # 1) System root categories (protected)
            for name, code, statement_type, cat_type, nb, display_order, status in SYSTEM_ROOT_CATEGORIES:
                obj, was_created = AccountCategory.objects.using(db).get_or_create(
                    code=code,
                    defaults={
                        "name": name,
                        "statement_type": statement_type,
                        "category_type": cat_type,
                        "normal_balance": nb,
                        "display_order": display_order,
                        "status": status,
                        "is_system": True,
                        "description": "Default NGO chart grouping.",
                        "parent_category": None,
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
                    if obj.category_type != cat_type:
                        obj.category_type = cat_type
                        changed = True
                    if obj.normal_balance != nb:
                        obj.normal_balance = nb
                        changed = True
                    if obj.display_order != display_order:
                        obj.display_order = display_order
                        changed = True
                    if (obj.status or "") != (status or ""):
                        obj.status = status
                        changed = True
                    if not obj.is_system:
                        obj.is_system = True
                        changed = True
                    if changed:
                        obj.save(using=db, skip_validation=True)
                        updated += 1

            parents_by_code = {
                o.code: o
                for o in AccountCategory.objects.using(db).filter(
                    code__in=[r[1] for r in SYSTEM_ROOT_CATEGORIES]
                )
            }

            # 2) Detailed categories linked to system parents
            for row in STANDARD_CATEGORIES:
                name, code, statement_type, display_order, status, cat_type, nb, parent_code = row
                parent = parents_by_code.get(parent_code)
                defaults = {
                    "name": name,
                    "statement_type": statement_type,
                    "category_type": cat_type,
                    "normal_balance": nb,
                    "display_order": display_order,
                    "status": status,
                    "is_system": False,
                    "parent_category": parent,
                }
                obj, was_created = AccountCategory.objects.using(db).get_or_create(
                    code=code,
                    defaults=defaults,
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
                    if obj.category_type != cat_type:
                        obj.category_type = cat_type
                        changed = True
                    if obj.normal_balance != nb:
                        obj.normal_balance = nb
                        changed = True
                    if obj.display_order != display_order:
                        obj.display_order = display_order
                        changed = True
                    if (obj.status or "") != (status or ""):
                        obj.status = status
                        changed = True
                    if obj.parent_category_id != (parent.pk if parent else None):
                        obj.parent_category = parent
                        changed = True
                    if changed:
                        obj.save(using=db, skip_validation=True)
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

