"""
Monitoring engine: platform and tenant health checks.
All writes go to default DB (diagnostics models).
Supports run_targeted(scope, tenant_id, service) for manual scans.
"""
from __future__ import annotations

import time
from django.db import connections
from django.conf import settings

from diagnostics.models import DiagnosticCheckRun, DiagnosticReport, Finding
from tenants.db import ensure_tenant_db_configured, tenant_db_alias
from tenants.models import Tenant


class MonitoringEngine:
    """Runs platform and tenant checks and records DiagnosticCheckRun + Finding."""

    def __init__(self, using: str = "default"):
        self.using = using

    def run_platform_checks(self, report: DiagnosticReport | None = None) -> list[DiagnosticCheckRun]:
        """Run platform-level checks (default DB, app registry)."""
        runs = []
        run = self._check_default_db(report=report)
        if run:
            runs.append(run)
        run = self._check_app_registry(report=report)
        if run:
            runs.append(run)
        return runs

    def _attach_report(self, run: DiagnosticCheckRun, report: DiagnosticReport | None) -> None:
        if report:
            run.report_id = report.id
            run.save(using=self.using, update_fields=["report_id"])

    def _check_default_db(self, report: DiagnosticReport | None = None) -> DiagnosticCheckRun | None:
        start = time.perf_counter()
        try:
            conn = connections["default"]
            conn.ensure_connection()
            conn.cursor().execute("SELECT 1")
            duration_ms = int((time.perf_counter() - start) * 1000)
            run = DiagnosticCheckRun.objects.using(self.using).create(
                scope=DiagnosticCheckRun.Scope.PLATFORM,
                check_type="default_db_connectivity",
                status=DiagnosticCheckRun.Status.SUCCESS,
                message="OK",
                duration_ms=duration_ms,
            )
            self._attach_report(run, report)
            return run
        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            run = DiagnosticCheckRun.objects.using(self.using).create(
                scope=DiagnosticCheckRun.Scope.PLATFORM,
                check_type="default_db_connectivity",
                status=DiagnosticCheckRun.Status.FAILURE,
                message=str(e)[:500],
                duration_ms=duration_ms,
            )
            self._attach_report(run, report)
            Finding.objects.using(self.using).create(
                run=run,
                code="DEFAULT_DB_DOWN",
                title="Default database unreachable",
                severity=Finding.Severity.CRITICAL,
                details={"error": str(e)},
            )
            return run

    def _check_app_registry(self, report: DiagnosticReport | None = None) -> DiagnosticCheckRun | None:
        start = time.perf_counter()
        try:
            from django.apps import apps
            for app_config in apps.get_app_configs():
                apps.get_app_config(app_config.label)
            duration_ms = int((time.perf_counter() - start) * 1000)
            run = DiagnosticCheckRun.objects.using(self.using).create(
                scope=DiagnosticCheckRun.Scope.PLATFORM,
                check_type="app_registry",
                status=DiagnosticCheckRun.Status.SUCCESS,
                message="OK",
                duration_ms=duration_ms,
            )
            self._attach_report(run, report)
            return run
        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            run = DiagnosticCheckRun.objects.using(self.using).create(
                scope=DiagnosticCheckRun.Scope.PLATFORM,
                check_type="app_registry",
                status=DiagnosticCheckRun.Status.FAILURE,
                message=str(e)[:500],
                duration_ms=duration_ms,
            )
            self._attach_report(run, report)
            Finding.objects.using(self.using).create(
                run=run,
                code="APP_REGISTRY_ERROR",
                title="App registry check failed",
                severity=Finding.Severity.HIGH,
                details={"error": str(e)},
            )
            return run

    def _check_cache(self, report: DiagnosticReport | None = None) -> DiagnosticCheckRun | None:
        start = time.perf_counter()
        try:
            from django.core.cache import cache
            cache.set("_diagnostics_health_check", 1, 10)
            ok = cache.get("_diagnostics_health_check") == 1
            duration_ms = int((time.perf_counter() - start) * 1000)
            run = DiagnosticCheckRun.objects.using(self.using).create(
                scope=DiagnosticCheckRun.Scope.PLATFORM,
                check_type="cache",
                status=DiagnosticCheckRun.Status.SUCCESS if ok else DiagnosticCheckRun.Status.FAILURE,
                message="OK" if ok else "Cache get/set failed",
                duration_ms=duration_ms,
            )
            self._attach_report(run, report)
            if not ok:
                Finding.objects.using(self.using).create(
                    run=run,
                    code="CACHE_ERROR",
                    title="Cache check failed",
                    severity=Finding.Severity.MEDIUM,
                    details={},
                )
            return run
        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            run = DiagnosticCheckRun.objects.using(self.using).create(
                scope=DiagnosticCheckRun.Scope.PLATFORM,
                check_type="cache",
                status=DiagnosticCheckRun.Status.FAILURE,
                message=str(e)[:500],
                duration_ms=duration_ms,
            )
            self._attach_report(run, report)
            Finding.objects.using(self.using).create(
                run=run,
                code="CACHE_ERROR",
                title="Cache unreachable",
                severity=Finding.Severity.MEDIUM,
                details={"error": str(e)},
            )
            return run

    def _check_api_health(self, report: DiagnosticReport | None = None) -> DiagnosticCheckRun | None:
        start = time.perf_counter()
        url = getattr(settings, "DIAGNOSTICS_HEALTH_URL", "http://127.0.0.1:8000/api/diagnostics/health/")
        try:
            import urllib.request
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                code = resp.getcode()
                body = resp.read().decode("utf-8", errors="ignore")[:200]
            duration_ms = int((time.perf_counter() - start) * 1000)
            ok = 200 <= code < 300
            run = DiagnosticCheckRun.objects.using(self.using).create(
                scope=DiagnosticCheckRun.Scope.PLATFORM,
                check_type="api_health",
                status=DiagnosticCheckRun.Status.SUCCESS if ok else DiagnosticCheckRun.Status.FAILURE,
                message=f"HTTP {code}" if ok else f"HTTP {code}: {body}",
                duration_ms=duration_ms,
            )
            self._attach_report(run, report)
            if not ok:
                Finding.objects.using(self.using).create(
                    run=run,
                    code="API_HEALTH_FAIL",
                    title="API health check failed",
                    severity=Finding.Severity.MEDIUM,
                    details={"url": url, "status_code": code},
                )
            return run
        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            run = DiagnosticCheckRun.objects.using(self.using).create(
                scope=DiagnosticCheckRun.Scope.PLATFORM,
                check_type="api_health",
                status=DiagnosticCheckRun.Status.FAILURE,
                message=str(e)[:500],
                duration_ms=duration_ms,
            )
            self._attach_report(run, report)
            Finding.objects.using(self.using).create(
                run=run,
                code="API_HEALTH_FAIL",
                title="API health check unreachable",
                severity=Finding.Severity.MEDIUM,
                details={"url": url, "error": str(e)},
            )
            return run

    def run_tenant_checks(self, report: DiagnosticReport | None = None, tenant_id: int | None = None) -> list[DiagnosticCheckRun]:
        """Run connectivity check for each tenant (or single tenant if tenant_id set)."""
        if tenant_id:
            tenants = list(Tenant.objects.using(self.using).filter(pk=tenant_id))
        else:
            tenants = list(
                Tenant.objects.using(self.using).filter(db_name__isnull=False).exclude(db_name="")
            )
        runs = []
        for tenant in tenants:
            run = self._check_tenant_db(tenant, report=report)
            if run:
                runs.append(run)
        return runs

    def _check_tenant_db(self, tenant, report: DiagnosticReport | None = None) -> DiagnosticCheckRun | None:
        start = time.perf_counter()
        alias = ensure_tenant_db_configured(tenant)
        try:
            conn = connections[alias]
            conn.ensure_connection()
            conn.cursor().execute("SELECT 1")
            duration_ms = int((time.perf_counter() - start) * 1000)
            run = DiagnosticCheckRun.objects.using(self.using).create(
                scope=DiagnosticCheckRun.Scope.TENANT,
                tenant_id=tenant.pk,
                tenant_slug=tenant.slug or "",
                check_type="tenant_db_connectivity",
                status=DiagnosticCheckRun.Status.SUCCESS,
                message="OK",
                duration_ms=duration_ms,
            )
            self._attach_report(run, report)
            return run
        except Exception as e:
            duration_ms = int((time.perf_counter() - start) * 1000)
            run = DiagnosticCheckRun.objects.using(self.using).create(
                scope=DiagnosticCheckRun.Scope.TENANT,
                tenant_id=tenant.pk,
                tenant_slug=tenant.slug or "",
                check_type="tenant_db_connectivity",
                status=DiagnosticCheckRun.Status.FAILURE,
                message=str(e)[:500],
                duration_ms=duration_ms,
            )
            self._attach_report(run, report)
            Finding.objects.using(self.using).create(
                run=run,
                code="TENANT_DB_DOWN",
                title=f"Tenant DB unreachable: {tenant.slug}",
                severity=Finding.Severity.HIGH,
                tenant_id=tenant.pk,
                details={"tenant_slug": tenant.slug, "alias": alias, "error": str(e)},
            )
            return run

    def run_all(self, report: DiagnosticReport | None = None) -> list[DiagnosticCheckRun]:
        """Run platform and tenant checks. Optionally link runs to report."""
        runs = []
        for r in self.run_platform_checks(report=report):
            runs.append(r)
        for r in self.run_tenant_checks(report=report):
            runs.append(r)
        return runs

    def run_targeted(
        self,
        scope: str,
        tenant_id: int | None = None,
        service: str | None = None,
        report: DiagnosticReport | None = None,
    ) -> list[DiagnosticCheckRun]:
        """
        Run only checks matching the target.
        scope: platform | tenant | database | api | service
        tenant_id: required for scope=tenant or database (single tenant)
        service: for scope=service, e.g. cache, default_db, app_registry
        """
        runs = []
        if scope == "platform":
            runs.extend(self.run_platform_checks(report=report))
            run = self._check_cache(report=report)
            if run:
                runs.append(run)
        elif scope == "tenant":
            if not tenant_id:
                return runs
            tenant = Tenant.objects.using(self.using).filter(pk=tenant_id).first()
            if tenant:
                run = self._check_tenant_db(tenant, report=report)
                if run:
                    runs.append(run)
        elif scope == "database":
            if tenant_id:
                tenant = Tenant.objects.using(self.using).filter(pk=tenant_id).first()
                if tenant:
                    run = self._check_tenant_db(tenant, report=report)
                    if run:
                        runs.append(run)
            else:
                run = self._check_default_db(report=report)
                if run:
                    runs.append(run)
        elif scope == "api":
            run = self._check_api_health(report=report)
            if run:
                runs.append(run)
        elif scope == "service":
            if service == "cache":
                run = self._check_cache(report=report)
            elif service == "default_db":
                run = self._check_default_db(report=report)
            elif service == "app_registry":
                run = self._check_app_registry(report=report)
            else:
                run = None
            if run:
                runs.append(run)
        return runs
