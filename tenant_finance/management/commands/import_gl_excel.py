"""
Post General Ledger–style Excel rows as journal entries for a grant/project.

Example (tenant DB must be configured on the Tenant record):

  python manage.py import_gl_excel --tenant myorg \\
    --file ./gl_rows.xlsx \\
    --grant-match PD2022534 \\
    --bank-account 1201 \\
    --actor-email admin@ngo.org

Default grant match also tries title \"Global Fund Malaria\" via substring.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from tenants.db import ensure_tenant_db_configured, tenant_db_alias
from tenants.models import Tenant

from tenant_finance.models import ChartAccount
from tenant_finance.services.gl_spreadsheet_import import (
    import_gl_rows_from_dataframe,
    read_gl_spreadsheet,
    resolve_grant,
)
from tenant_users.models import TenantUser


class Command(BaseCommand):
    help = "Import GL-style Excel: one posted journal per row (Dr expense / Cr bank) for a grant."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="Tenant slug or id (public DB).")
        parser.add_argument("--file", required=True, help="Path to .xlsx file (first sheet).")
        parser.add_argument(
            "--grant-match",
            default="PD2022534",
            help="Substring to find Grant.code or Grant.title (default: PD2022534).",
        )
        parser.add_argument(
            "--project-match",
            default="",
            help="Optional substring for Project.code/name if grant not found by --grant-match.",
        )
        parser.add_argument(
            "--bank-account",
            required=True,
            help="Chart of accounts code for the credit leg (e.g. operating bank 1201).",
        )
        parser.add_argument(
            "--default-expense",
            default="5351",
            help="Fallback expense GL code when row has no account and budget line has no GL (default 5351).",
        )
        parser.add_argument(
            "--actor-email",
            required=True,
            help="Tenant user email (posting user; should be allowed to post, e.g. tenant admin).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and validate only; do not create journals.",
        )

    def handle(self, *args, **options):
        tenant_arg = options["tenant"]
        tenant = Tenant.objects.filter(slug=tenant_arg).first() or Tenant.objects.filter(pk=tenant_arg).first()
        if not tenant:
            raise CommandError("Tenant not found.")
        if not tenant.db_name:
            raise CommandError("Tenant has no db_name; provision tenant DB first.")

        ensure_tenant_db_configured(tenant)
        using = tenant_db_alias(tenant)

        grant = resolve_grant(
            using,
            grant_substring=options["grant_match"],
            project_substring=(options["project_match"] or None) or None,
        )
        if not grant:
            raise CommandError(
                f"No active grant found for --grant-match={options['grant_match']!r} "
                f"(and project-match if set). Expected e.g. SOM/PCA2021252/PD2022534 — Global Fund Malaria."
            )

        actor = TenantUser.objects.using(using).filter(email__iexact=options["actor_email"].strip()).first()
        if not actor:
            raise CommandError(f"No tenant user with email {options['actor_email']!r}.")

        bank = ChartAccount.objects.using(using).filter(code=options["bank_account"].strip()).first()
        if not bank:
            raise CommandError(f"Bank / credit account code {options['bank_account']!r} not found.")

        try:
            df = read_gl_spreadsheet(options["file"])
        except Exception as exc:
            raise CommandError(f"Could not read Excel: {exc}") from exc

        self.stdout.write(
            f"Tenant DB: {using}\nGrant: {grant.code} — {grant.title} (id={grant.pk})\n"
            f"Project: {grant.project.code} — {grant.project.name}\nDonor: {grant.donor.name}\n"
        )

        results = import_gl_rows_from_dataframe(
            df,
            using=using,
            grant=grant,
            actor=actor,
            bank_account=bank,
            default_expense_code=options["default_expense"],
            dry_run=options["dry_run"],
        )

        posted = skipped = errors = 0
        for r in results:
            if r.status == "posted":
                posted += 1
                msg = f"row {r.row_index} {r.document_reference}: {r.status}"
                if r.entry_id:
                    msg += f" entry_id={r.entry_id}"
                if r.message:
                    msg += f" — {r.message}"
                self.stdout.write(msg)
            elif r.status == "skipped":
                skipped += 1
                self.stdout.write(f"row {r.row_index} {r.document_reference}: skipped — {r.message}")
            else:
                errors += 1
                self.stdout.write(self.style.ERROR(f"row {r.row_index} {r.document_reference}: {r.message}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. posted={posted} skipped={skipped} errors={errors} dry_run={options['dry_run']}"
            )
        )
