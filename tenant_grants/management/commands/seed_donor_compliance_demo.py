"""
Idempotent demo seed for Donor Compliance Monitoring (tenant DB).

Creates (if missing):
  - 2 donors (including WARDI Relief Development Initiatives)
  - 2 projects + 2 active grants with award amounts
  - 5 active donor restrictions (mixed compliance outcomes)
  - Posted journal entries with expense lines

Run after tenant DB exists:
  python manage.py migrate_tenant --tenant YOUR_SLUG
  python manage.py seed_donor_compliance_demo --tenant YOUR_SLUG
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tenants.db import ensure_tenant_db_configured, tenant_db_alias
from tenants.models import Tenant


class Command(BaseCommand):
    help = "Seed donor compliance demo data on a tenant database (idempotent)."

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
        from tenant_grants.models import Donor, DonorRestriction, Grant, Project

        ensure_default_currencies(db)
        usd = Currency.objects.using(db).filter(code="USD").first()
        if not usd:
            raise CommandError("Could not resolve USD currency on tenant DB.")

        with transaction.atomic(using=db):
            d1, _ = Donor.objects.using(db).get_or_create(
                code="DEMO-WARDI",
                defaults={
                    "name": "WARDI Relief Development Initiatives",
                    "status": Donor.Status.ACTIVE,
                },
            )
            if d1.name != "WARDI Relief Development Initiatives":
                Donor.objects.using(db).filter(pk=d1.pk).update(
                    name="WARDI Relief Development Initiatives"
                )
                d1.refresh_from_db()

            d2, _ = Donor.objects.using(db).get_or_create(
                code="DEMO-UNICEF",
                defaults={"name": "UNICEF Demo Partner", "status": Donor.Status.ACTIVE},
            )

            p1, _ = Project.objects.using(db).get_or_create(
                code="DEMO-P-WARDI",
                defaults={
                    "name": "WARDI Emergency Response",
                    "donor": d1,
                    "status": Project.Status.ACTIVE,
                    "start_date": date(2025, 1, 1),
                    "end_date": date(2028, 12, 31),
                },
            )
            p2, _ = Project.objects.using(db).get_or_create(
                code="DEMO-P-UNICEF",
                defaults={
                    "name": "UNICEF WASH Program",
                    "donor": d2,
                    "status": Project.Status.ACTIVE,
                    "start_date": date(2025, 1, 1),
                    "end_date": date(2028, 12, 31),
                },
            )

            g1, _ = Grant.objects.using(db).get_or_create(
                code="DEMO-G-WARDI-01",
                defaults={
                    "title": "WARDI Grant One",
                    "donor": d1,
                    "project": p1,
                    "status": Grant.Status.ACTIVE,
                    "award_amount": Decimal("100000.00"),
                    "currency": usd,
                    "start_date": date(2025, 1, 1),
                    "end_date": date(2028, 12, 31),
                },
            )
            Grant.objects.using(db).filter(pk=g1.pk).update(
                award_amount=Decimal("100000.00"),
                status=Grant.Status.ACTIVE,
                project=p1,
                donor=d1,
                currency=usd,
            )

            g2, _ = Grant.objects.using(db).get_or_create(
                code="DEMO-G-UNICEF-01",
                defaults={
                    "title": "UNICEF Grant One",
                    "donor": d2,
                    "project": p2,
                    "status": Grant.Status.ACTIVE,
                    "award_amount": Decimal("50000.00"),
                    "currency": usd,
                    "start_date": date(2025, 1, 1),
                    "end_date": date(2028, 12, 31),
                },
            )
            Grant.objects.using(db).filter(pk=g2.pk).update(
                award_amount=Decimal("50000.00"),
                status=Grant.Status.ACTIVE,
                project=p2,
                donor=d2,
                currency=usd,
            )

            exp, _ = ChartAccount.objects.using(db).get_or_create(
                code="DEMO-6100",
                defaults={
                    "name": "Program expenses (demo)",
                    "type": ChartAccount.Type.EXPENSE,
                    "statement_type": ChartAccount.StatementType.INCOME_EXPENDITURE,
                    "is_active": True,
                },
            )
            ap, _ = ChartAccount.objects.using(db).get_or_create(
                code="DEMO-2000",
                defaults={
                    "name": "Accounts payable (demo)",
                    "type": ChartAccount.Type.LIABILITY,
                    "statement_type": ChartAccount.StatementType.BALANCE_SHEET,
                    "is_active": True,
                },
            )

            def ensure_restriction(code_suffix: str, **kwargs):
                r = DonorRestriction.objects.using(db).filter(restriction_code=code_suffix).first()
                if r:
                    for k, v in kwargs.items():
                        setattr(r, k, v)
                    r.save(using=db)
                    return r
                dr = DonorRestriction(**kwargs)
                dr.save(using=db)
                DonorRestriction.objects.using(db).filter(pk=dr.pk).update(restriction_code=code_suffix)
                dr.refresh_from_db()
                return dr

            # Posted expense on g1 is 24,000 (max line 9,000) for Mar 2026 — same pool for rules 1–4.
            # 1) Warning — 25% cap → allowed 25,000; spend 24,000 > 90% of allowed (22,500)
            ensure_restriction(
                "DEMO-DRC-000001",
                donor=d1,
                grant=g1,
                category=DonorRestriction.Category.BUDGET,
                restriction_type=DonorRestriction.RestrictionType.BUDGET_CATEGORY_CAP,
                compliance_level=DonorRestriction.ComplianceLevel.MANDATORY,
                status=DonorRestriction.Status.ACTIVE,
                applies_scope=DonorRestriction.AppliesScope.GRANT,
                description="Demo: 25% of award cap — high utilization (warning band).",
                max_budget_percentage=Decimal("25.00"),
                effective_start=date(2025, 1, 1),
                effective_end=date(2028, 12, 31),
            )
            # 2) Compliant — 50% cap
            ensure_restriction(
                "DEMO-DRC-000002",
                donor=d1,
                grant=g1,
                category=DonorRestriction.Category.BUDGET,
                restriction_type=DonorRestriction.RestrictionType.BUDGET_CATEGORY_CAP,
                compliance_level=DonorRestriction.ComplianceLevel.MANDATORY,
                status=DonorRestriction.Status.ACTIVE,
                applies_scope=DonorRestriction.AppliesScope.GRANT,
                description="Demo: 50% cap — spend comfortably inside limit.",
                max_budget_percentage=Decimal("50.00"),
                effective_start=date(2025, 1, 1),
                effective_end=date(2028, 12, 31),
            )
            # 3) Breach — 20% cap → allowed 20,000 < spend 24,000
            ensure_restriction(
                "DEMO-DRC-000003",
                donor=d1,
                grant=g1,
                category=DonorRestriction.Category.BUDGET,
                restriction_type=DonorRestriction.RestrictionType.BUDGET_CATEGORY_CAP,
                compliance_level=DonorRestriction.ComplianceLevel.MANDATORY,
                status=DonorRestriction.Status.ACTIVE,
                applies_scope=DonorRestriction.AppliesScope.GRANT,
                description="Demo: 20% cap — posted spend exceeds allowed budget.",
                max_budget_percentage=Decimal("20.00"),
                effective_start=date(2025, 1, 1),
                effective_end=date(2028, 12, 31),
            )
            # 4) Per-txn compliant (max line 9,000 < 10,000)
            ensure_restriction(
                "DEMO-DRC-000004",
                donor=d1,
                grant=g1,
                category=DonorRestriction.Category.PROCUREMENT,
                restriction_type=DonorRestriction.RestrictionType.PROC_MIN_QUOTES,
                compliance_level=DonorRestriction.ComplianceLevel.MANDATORY,
                status=DonorRestriction.Status.ACTIVE,
                applies_scope=DonorRestriction.AppliesScope.GRANT,
                description="Demo: max expense per transaction 10,000 — all lines within limit.",
                max_expense_per_transaction=Decimal("10000.00"),
                effective_start=date(2025, 1, 1),
                effective_end=date(2028, 12, 31),
            )
            # 5) Not applicable (reporting)
            ensure_restriction(
                "DEMO-DRC-000005",
                donor=d2,
                grant=g2,
                category=DonorRestriction.Category.REPORTING,
                restriction_type=DonorRestriction.RestrictionType.REP_FINANCIAL_FREQUENCY,
                compliance_level=DonorRestriction.ComplianceLevel.RECOMMENDED,
                status=DonorRestriction.Status.ACTIVE,
                applies_scope=DonorRestriction.AppliesScope.GRANT,
                description="Demo: reporting rule — not evaluated from expenses.",
                effective_start=date(2025, 1, 1),
                effective_end=date(2028, 12, 31),
            )

            # Posted journals (period Mar 2026) — g1 total expense 8k+7k+9k = 24k; max line 9k
            demo_day = date(2026, 3, 15)
            ref = "DEMO-JNL-COMP-001"
            if not JournalEntry.objects.using(db).filter(reference=ref).exists():
                je = JournalEntry.objects.using(db).create(
                    reference=ref,
                    memo="Demo compliance seed",
                    entry_date=demo_day,
                    currency=usd,
                    grant=g1,
                    status=JournalEntry.Status.POSTED,
                )
                JournalLine.objects.using(db).create(
                    entry=je, account=exp, debit=Decimal("8000.00"), credit=Decimal("0"), description="Demo spend A"
                )
                JournalLine.objects.using(db).create(
                    entry=je, account=ap, debit=Decimal("0"), credit=Decimal("8000.00"), description="Balancing"
                )

            ref2 = "DEMO-JNL-COMP-002"
            if not JournalEntry.objects.using(db).filter(reference=ref2).exists():
                je = JournalEntry.objects.using(db).create(
                    reference=ref2,
                    memo="Demo compliance seed B",
                    entry_date=demo_day,
                    currency=usd,
                    grant=g1,
                    status=JournalEntry.Status.POSTED,
                )
                JournalLine.objects.using(db).create(
                    entry=je, account=exp, debit=Decimal("7000.00"), credit=Decimal("0"), description="Demo spend B"
                )
                JournalLine.objects.using(db).create(
                    entry=je, account=ap, debit=Decimal("0"), credit=Decimal("7000.00"), description="Balancing"
                )

            ref3 = "DEMO-JNL-COMP-003"
            if not JournalEntry.objects.using(db).filter(reference=ref3).exists():
                je = JournalEntry.objects.using(db).create(
                    reference=ref3,
                    memo="Demo line C",
                    entry_date=demo_day,
                    currency=usd,
                    grant=g1,
                    status=JournalEntry.Status.POSTED,
                )
                JournalLine.objects.using(db).create(
                    entry=je, account=exp, debit=Decimal("9000.00"), credit=Decimal("0"), description="Demo spend C"
                )
                JournalLine.objects.using(db).create(
                    entry=je, account=ap, debit=Decimal("0"), credit=Decimal("9000.00"), description="Balancing"
                )

            # Small spend on g2 for context
            ref4 = "DEMO-JNL-COMP-004"
            if not JournalEntry.objects.using(db).filter(reference=ref4).exists():
                je = JournalEntry.objects.using(db).create(
                    reference=ref4,
                    memo="Demo UNICEF spend",
                    entry_date=demo_day,
                    currency=usd,
                    grant=g2,
                    status=JournalEntry.Status.POSTED,
                )
                JournalLine.objects.using(db).create(
                    entry=je, account=exp, debit=Decimal("2500.00"), credit=Decimal("0"), description="UNICEF demo"
                )
                JournalLine.objects.using(db).create(
                    entry=je, account=ap, debit=Decimal("0"), credit=Decimal("2500.00"), description="Balancing"
                )

        self.stdout.write(self.style.SUCCESS(f"Donor compliance demo data ensured on '{db}'."))
