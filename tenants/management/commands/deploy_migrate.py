"""
Single-process migration step for production deploys.

Runs `migrate` on the control-plane database (default), then optionally
`migrate_all_tenants`. Use this from `scripts/deploy.sh` or webhooks instead of
shell-chaining two separate `docker compose exec` calls (avoids ordering/race
issues and keeps logs in one stream).

`tenant_grants` / `tenant_finance` tables (e.g. tenant_grants_donor) are NOT on
the default DB — they live on each tenant database. If you only run
`migrate` on default, tenant DBs still need migrate_all_tenants.
"""

from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Migrate default (control plane), then optionally all tenant databases. "
        "Prefer this over separate migrate + migrate_all_tenants in deploy hooks."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-tenant-databases",
            action="store_true",
            help="Only migrate the default database; do not run migrate_all_tenants.",
        )
        parser.add_argument(
            "--noinput",
            action="store_true",
            help="Non-interactive (recommended for deploy).",
        )

    def handle(self, *args, **options):
        skip_tenants = options["skip_tenant_databases"]
        verbosity = 1

        self.stdout.write(self.style.NOTICE("==> [deploy_migrate] Control-plane: migrate (database=default)"))
        call_command("migrate", interactive=False, verbosity=verbosity)

        if skip_tenants:
            self.stdout.write(
                self.style.WARNING(
                    "==> [deploy_migrate] Skipping tenant databases (--skip-tenant-databases)."
                )
            )
            return

        self.stdout.write(
            self.style.NOTICE(
                "==> [deploy_migrate] Tenant DBs: migrate_all_tenants "
                "(tenant_grants, tenant_finance, … are applied here, not on default)"
            )
        )
        call_command("migrate_all_tenants", noinput=True)
