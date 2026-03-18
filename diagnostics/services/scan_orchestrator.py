"""
Manual scan orchestrator: run targeted checks, RCA, optional remediation, build DiagnosticReport.
"""
from __future__ import annotations

from django.utils import timezone

from diagnostics.models import DiagnosticReport, DiagnosticCheckRun, Finding, Incident, RemediationLog
from diagnostics.services import MonitoringEngine, RCAEngine, RemediationRunner


def run_manual_scan(
    scope: str,
    tenant_id: int | None = None,
    service: str | None = None,
    apply_fixes: bool = False,
    using: str = "default",
) -> DiagnosticReport:
    """
    Run a manual diagnostic scan and optionally apply fixes.
    scope: platform | tenant | database | api | service
    Returns the DiagnosticReport (status completed or failed).
    """
    target = {"scope": scope}
    if tenant_id:
        target["tenant_id"] = tenant_id
    if service:
        target["service"] = service

    report = DiagnosticReport.objects.using(using).create(
        trigger=DiagnosticReport.Trigger.MANUAL,
        target=target,
        status=DiagnosticReport.Status.RUNNING,
    )
    try:
        engine = MonitoringEngine(using=using)
        runs = engine.run_targeted(scope=scope, tenant_id=tenant_id, service=service, report=report)
        run_ids = [r.id for r in runs]

        # RCA for high-severity findings from this report's runs
        rca = RCAEngine(using=using)
        findings = Finding.objects.using(using).filter(
            run_id__in=run_ids,
            severity__in=(Finding.Severity.CRITICAL, Finding.Severity.HIGH, Finding.Severity.MEDIUM),
        )
        incidents_created = []
        for finding in findings:
            inc = rca.run_for_finding(finding, report=report)
            if inc and inc.report_id == report.id:
                incidents_created.append(inc)

        remediations_applied = []
        if apply_fixes:
            runner = RemediationRunner(using=using)
            for inc in incidents_created:
                logs = runner.run_suggested_actions(inc.id, approved=True)
                for log in logs:
                    remediations_applied.append({
                        "incident_id": inc.id,
                        "action_code": log.action_code,
                        "status": log.status,
                        "message": log.message,
                    })

        success_count = sum(1 for r in runs if r.status == DiagnosticCheckRun.Status.SUCCESS)
        failure_count = len(runs) - success_count
        report.status = DiagnosticReport.Status.COMPLETED
        report.finished_at = timezone.now()
        report.summary = {
            "total_checks": len(runs),
            "success_count": success_count,
            "failure_count": failure_count,
            "incidents_created": len(incidents_created),
            "remediations_applied": len(remediations_applied),
            "run_ids": run_ids,
        }
        report.save(using=using, update_fields=["status", "finished_at", "summary"])
        return report
    except Exception as e:
        report.status = DiagnosticReport.Status.FAILED
        report.finished_at = timezone.now()
        report.error_message = str(e)[:1000]
        report.save(using=using, update_fields=["status", "finished_at", "error_message"])
        raise
