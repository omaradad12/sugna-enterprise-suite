"""
Idempotent demo seed for Grant Financial Reports (tenant DB).

Creates (if missing):
  - Donor Action Medeor
  - Project + active grant "Water provision" (code 6002400)
  - Grant budget lines: Supplies 20,000; Transport 5,000; Staff 10,000
  - Two posted journal entries: Supplies 3,000; Transport 1,000

Expected on default March-period report: Budget 35,000 · Spent 4,000 · Remaining 31,000.

  python manage.py migrate_tenant --tenant YOUR_SLUG
  python manage.py seed_grant_financial_reports_demo --tenant YOUR_SLUG
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tenants.db import ensure_tenant_db_configured, tenant_db_alias
from tenants.models import Tenant


class Command(BaseCommand):
    help = "Seed grant financial reports demo data on a tenant database (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="Tenant slug or primary key.")

    def handle(self, *args, **options):
        tenant_arg = options["tenant"]
        tenant = Tenant.objects.filter(slug=tenant_arg).first() or Tenant.objects.filter(
            pk=tenant_arg
        ).first()
        if not tenant or not tenant.db_name:
            raise CommandError("Tenant not found or has no db_name.")
        ensure_tenant_db_configured(tenant)
        db = tenant_db_alias(tenant)

        from tenant_finance.models import ChartAccount, Currency, JournalEntry, JournalLine
        from tenant_finance.models import ensure_default_currencies
        from tenant_grants.models import BudgetLine, Donor, Grant, Project

        ensure_default_currencies(db)
        usd = Currency.objects.using(db).filter(code="USD").first()
        if not usd:
            raise CommandError("Could not resolve USD currency on tenant DB.")

        with transaction.atomic(using=db):
            donor, _ = Donor.objects.using(db).get_or_create(
                code="GFR-ACTION-MED",
                defaults={
                    "name": "Action Medeor",
                    "status": Donor.Status.ACTIVE,
                },
            )
            Donor.objects.using(db).filter(pk=donor.pk).update(
                name="Action Medeor",
                status=Donor.Status.ACTIVE,
            )
            donor.refresh_from_db()

            project, _ = Project.objects.using(db).get_or_create(
                code="GFR-WASH-DEMO",
                defaults={
                    "name": "Water & sanitation demo project",
                    "donor": donor,
                    "status": Project.Status.ACTIVE,
                    "start_date": date(2025, 1, 1),
                    "end_date": date(2028, 12, 31),
                },
            )
            Project.objects.using(db).filter(pk=project.pk).update(
                donor=donor,
                status=Project.Status.ACTIVE,
            )

            grant, _ = Grant.objects.using(db).get_or_create(
                code="6002400",
                defaults={
                    "title": "Water provision",
                    "donor": donor,
                    "project": project,
                    "status": Grant.Status.ACTIVE,
                    "award_amount": Decimal("35000.00"),
                    "currency": usd,
                    "start_date": date(2025, 1, 1),
                    "end_date": date(2028, 12, 31),
                },
            )
            Grant.objects.using(db).filter(pk=grant.pk).update(
                title="Water provision",
                donor=donor,
                project=project,
                status=Grant.Status.ACTIVE,
                award_amount=Decimal("35000.00"),
                currency=usd,
            )
            grant.refresh_from_db()

            exp, _ = ChartAccount.objects.using(db).get_or_create(
                code="GFR-6100-SUP",
                defaults={
                    "name": "Program expenses — supplies (demo)",
                    "type": ChartAccount.Type.EXPENSE,
                    "statement_type": ChartAccount.StatementType.INCOME_EXPENDITURE,
                    "is_active": True,
                },
            )
            exp_tr, _ = ChartAccount.objects.using(db).get_or_create(
                code="GFR-6101-TRN",
                defaults={
                    "name": "Program expenses — transport (demo)",
                    "type": ChartAccount.Type.EXPENSE,
                    "statement_type": ChartAccount.StatementType.INCOME_EXPENDITURE,
                    "is_active": True,
                },
            )
            exp_st, _ = ChartAccount.objects.using(db).get_or_create(
                code="GFR-6102-STF",
                defaults={
                    "name": "Program expenses — staff (demo)",
                    "type": ChartAccount.Type.EXPENSE,
                    "statement_type": ChartAccount.StatementType.INCOME_EXPENDITURE,
                    "is_active": True,
                },
            )

            def ensure_budget_line(
                *,
                line_code: str,
                category: str,
                amount: Decimal,
                account,
            ) -> None:
                bl = (
                    BudgetLine.objects.using(db)
                    .filter(grant=grant, budget_code=line_code)
                    .first()
                )
                if bl:
                    BudgetLine.objects.using(db).filter(pk=bl.pk).update(amount=amount)
                else:
                    BudgetLine.objects.using(db).create(
                        grant=grant,
                        project=project,
                        budget_code=line_code,
                        category=category,
                        amount=amount,
                        account=account,
                    )

            ensure_budget_line(
                line_code="GFR-DEMO-SUP",
                category="Supplies",
                amount=Decimal("20000.00"),
                account=exp,
            )
            ensure_budget_line(
                line_code="GFR-DEMO-TRN",
                category="Transport",
                amount=Decimal("5000.00"),
                account=exp_tr,
            )
            ensure_budget_line(
                line_code="GFR-DEMO-STF",
                category="Staff",
                amount=Decimal("10000.00"),
                account=exp_st,
            )
            ap, _ = ChartAccount.objects.using(db).get_or_create(
                code="GFR-2000-AP",
                defaults={
                    "name": "Accounts payable (GFR demo)",
                    "type": ChartAccount.Type.LIABILITY,
                    "statement_type": ChartAccount.StatementType.BALANCE_SHEET,
                    "is_active": True,
                },
            )

            demo_day = date(2026, 3, 10)
            ref_supplies = "GFR-DEMO-SUPPLIES-3000"
            if not JournalEntry.objects.using(db).filter(reference=ref_supplies).exists():
                je = JournalEntry.objects.using(db).create(
                    reference=ref_supplies,
                    memo="Demo: supplies expense (grant financial reports)",
                    entry_date=demo_day,
                    posting_date=demo_day,
                    currency=usd,
                    grant=grant,
                    donor=donor,
                    status=JournalEntry.Status.POSTED,
                    source_type=JournalEntry.SourceType.MANUAL,
                    journal_type="adjustment",
                )
                JournalLine.objects.using(db).create(
                    entry=je,
                    account=exp,
                    grant=grant,
                    debit=Decimal("3000.00"),
                    credit=Decimal("0"),
                    description="Supplies",
                )
                JournalLine.objects.using(db).create(
                    entry=je,
                    account=ap,
                    debit=Decimal("0"),
                    credit=Decimal("3000.00"),
                    description="Balancing",
                )

            ref_transport = "GFR-DEMO-TRANSPORT-1000"
            if not JournalEntry.objects.using(db).filter(reference=ref_transport).exists():
                je2 = JournalEntry.objects.using(db).create(
                    reference=ref_transport,
                    memo="Demo: transport expense (grant financial reports)",
                    entry_date=demo_day,
                    posting_date=demo_day,
                    currency=usd,
                    grant=grant,
                    donor=donor,
                    status=JournalEntry.Status.POSTED,
                    source_type=JournalEntry.SourceType.PAYMENT_VOUCHER,
                    journal_type="payment_voucher",
                )
                JournalLine.objects.using(db).create(
                    entry=je2,
                    account=exp_tr,
                    grant=grant,
                    debit=Decimal("1000.00"),
                    credit=Decimal("0"),
                    description="Transport",
                )
                JournalLine.objects.using(db).create(
                    entry=je2,
                    account=ap,
                    debit=Decimal("0"),
                    credit=Decimal("1000.00"),
                    description="Balancing",
                )

        self.stdout.write(self.style.SUCCESS(f"Grant financial reports demo data ensured on tenant DB {db!r}."))
