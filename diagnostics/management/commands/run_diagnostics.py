"""
Run platform and tenant checks, create findings, run RCA and optionally create incidents.
Automatic mode: use --auto-remediate to run allowed remediation actions for open incidents.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from diagnostics.models import Finding, Incident
from diagnostics.services import MonitoringEngine, RCAEngine, RemediationRunner


class Command(BaseCommand):
    help = "Run self-healing diagnostics: platform + tenant checks, RCA, and optionally auto-remediation."

    def add_arguments(self, parser):
        parser.add_argument(
            "--platform-only",
            action="store_true",
            help="Run only platform-level checks.",
        )
        parser.add_argument(
            "--tenant-only",
            action="store_true",
            help="Run only tenant-level checks.",
        )
        parser.add_argument(
            "--no-rca",
            action="store_true",
            help="Skip creating/updating incidents from findings.",
        )
        parser.add_argument(
            "--auto-remediate",
            action="store_true",
            help="Run allowed remediation actions for open incidents (automatic mode).",
        )

    def handle(self, *args, **options):
        engine = MonitoringEngine()
        if options["platform_only"]:
            runs = engine.run_platform_checks()
            self.stdout.write(self.style.SUCCESS(f"Platform checks: {len(runs)} run(s)."))
        elif options["tenant_only"]:
            runs = engine.run_tenant_checks()
            self.stdout.write(self.style.SUCCESS(f"Tenant checks: {len(runs)} run(s)."))
        else:
            runs_platform = engine.run_platform_checks()
            runs_tenant = engine.run_tenant_checks()
            self.stdout.write(self.style.SUCCESS(f"Platform checks: {len(runs_platform)} run(s)."))
            self.stdout.write(self.style.SUCCESS(f"Tenant checks: {len(runs_tenant)} run(s)."))
        if not options["no_rca"]:
            rca = RCAEngine()
            since = timezone.now() - timedelta(minutes=10)
            high = Finding.objects.filter(
                severity__in=(Finding.Severity.CRITICAL, Finding.Severity.HIGH),
                run__isnull=False,
                created_at__gte=since,
            ).order_by("-created_at")[:50]
            for finding in high:
                rca.run_for_finding(finding)
            self.stdout.write(self.style.SUCCESS(f"RCA: processed {len(high)} finding(s)."))
        from django.conf import settings
        auto_remediate = options["auto_remediate"] or getattr(settings, "DIAGNOSTICS_AUTO_REMEDIATE", False)
        if auto_remediate:
            runner = RemediationRunner()
            open_incidents = Incident.objects.filter(
                status__in=(Incident.Status.OPEN, Incident.Status.INVESTIGATING)
            )[:20]
            total_logs = 0
            for inc in open_incidents:
                logs = runner.run_suggested_actions(inc.id, approved=False)
                total_logs += len(logs)
            self.stdout.write(self.style.SUCCESS(f"Auto-remediation: {total_logs} action(s) run for {len(open_incidents)} incident(s)."))
        self.stdout.write(self.style.SUCCESS("Diagnostics run complete."))
