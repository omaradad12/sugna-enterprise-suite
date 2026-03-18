"""
REST API for diagnostics: checks, findings, incidents, remediation.
Requires staff/superuser (platform admin).
"""
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from diagnostics.models import (
    DiagnosticCheckRun,
    DiagnosticReport,
    Finding,
    Incident,
    RemediationLog,
)
from diagnostics.services.remediation_runner import RemediationRunner
from diagnostics.services.scan_orchestrator import run_manual_scan


def _staff_api(view):
    return login_required(login_url="/platform/login/")(staff_member_required(login_url="/platform/login/")(view))


@require_GET
def health(request):
    """
    Platform health. Default: minimal for load balancer (no auth).
    ?full=1: extended checks (tenant DBs, cache); requires staff when full=1.
    """
    from django.db import connections
    payload = {"status": "ok", "database": "connected"}
    try:
        connections["default"].ensure_connection()
        connections["default"].cursor().execute("SELECT 1")
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=503)

    if request.GET.get("full") not in ("1", "true", "yes"):
        return JsonResponse(payload)

    # Extended: require staff
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({"status": "error", "message": "Full health requires staff"}, status=403)

    # Tenant DBs
    from tenants.db import ensure_tenant_db_configured
    from tenants.models import Tenant
    tenants_status = []
    for tenant in Tenant.objects.filter(db_name__isnull=False).exclude(db_name="")[:50]:
        try:
            alias = ensure_tenant_db_configured(tenant)
            connections[alias].ensure_connection()
            connections[alias].cursor().execute("SELECT 1")
            tenants_status.append({"slug": tenant.slug, "status": "ok"})
        except Exception as e:
            tenants_status.append({"slug": tenant.slug, "status": "error", "message": str(e)[:200]})
    payload["tenants"] = tenants_status

    # Cache
    try:
        from django.core.cache import cache
        cache.set("_health_check", 1, 5)
        if cache.get("_health_check") == 1:
            payload["cache"] = "ok"
        else:
            payload["cache"] = "error"
    except Exception as e:
        payload["cache"] = "error"
        payload["cache_message"] = str(e)[:200]

    return JsonResponse(payload)


@require_GET
@_staff_api
def check_runs_list(request):
    """List diagnostic check runs with optional filters."""
    qs = DiagnosticCheckRun.objects.all().order_by("-created_at")[:200]
    scope = request.GET.get("scope")
    if scope:
        qs = qs.filter(scope=scope)
    tenant_id = request.GET.get("tenant_id")
    if tenant_id:
        qs = qs.filter(tenant_id=tenant_id)
    date_from = request.GET.get("date_from")
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    date_to = request.GET.get("date_to")
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    runs = [
        {
            "id": r.id,
            "scope": r.scope,
            "tenant_id": r.tenant_id,
            "tenant_slug": r.tenant_slug,
            "check_type": r.check_type,
            "status": r.status,
            "message": r.message,
            "duration_ms": r.duration_ms,
            "created_at": r.created_at.isoformat(),
        }
        for r in qs
    ]
    return JsonResponse({"results": runs, "count": len(runs)})


@require_GET
@_staff_api
def check_run_detail(request, run_id):
    """Single check run with findings."""
    run = get_object_or_404(DiagnosticCheckRun, pk=run_id)
    findings = [
        {
            "id": f.id,
            "code": f.code,
            "title": f.title,
            "severity": f.severity,
            "details": f.details,
            "tenant_id": f.tenant_id,
            "created_at": f.created_at.isoformat(),
        }
        for f in run.findings.all()
    ]
    return JsonResponse({
        "id": run.id,
        "scope": run.scope,
        "tenant_id": run.tenant_id,
        "tenant_slug": run.tenant_slug,
        "check_type": run.check_type,
        "status": run.status,
        "message": run.message,
        "duration_ms": run.duration_ms,
        "created_at": run.created_at.isoformat(),
        "findings": findings,
    })


@require_GET
@_staff_api
def findings_list(request):
    """List findings with optional filters."""
    qs = Finding.objects.all().order_by("-created_at")[:200]
    severity = request.GET.get("severity")
    if severity:
        qs = qs.filter(severity=severity)
    run_id = request.GET.get("run_id")
    if run_id:
        qs = qs.filter(run_id=run_id)
    code = request.GET.get("code")
    if code:
        qs = qs.filter(code=code)
    findings = [
        {
            "id": f.id,
            "run_id": f.run_id,
            "code": f.code,
            "title": f.title,
            "severity": f.severity,
            "details": f.details,
            "tenant_id": f.tenant_id,
            "created_at": f.created_at.isoformat(),
        }
        for f in qs
    ]
    return JsonResponse({"results": findings, "count": len(findings)})


@require_GET
@_staff_api
def incidents_list(request):
    """List incidents with optional filters."""
    qs = Incident.objects.all().order_by("-created_at")[:200]
    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)
    severity = request.GET.get("severity")
    if severity:
        qs = qs.filter(severity=severity)
    tenant_id = request.GET.get("tenant_id")
    if tenant_id:
        qs = qs.filter(tenant_id=tenant_id)
    incidents = [
        {
            "id": i.id,
            "title": i.title,
            "severity": i.severity,
            "status": i.status,
            "scope": i.scope,
            "tenant_id": i.tenant_id,
            "tenant_slug": i.tenant_slug,
            "root_cause_summary": i.root_cause_summary,
            "suggested_actions": i.suggested_actions,
            "created_at": i.created_at.isoformat(),
            "updated_at": i.updated_at.isoformat(),
            "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
        }
        for i in qs
    ]
    return JsonResponse({"results": incidents, "count": len(incidents)})


@require_GET
@_staff_api
def incident_detail(request, incident_id):
    """Single incident with remediation logs."""
    inc = get_object_or_404(Incident, pk=incident_id)
    logs = [
        {
            "id": l.id,
            "action_code": l.action_code,
            "status": l.status,
            "started_at": l.started_at.isoformat(),
            "finished_at": l.finished_at.isoformat() if l.finished_at else None,
            "message": l.message,
        }
        for l in inc.remediation_logs.all()
    ]
    return JsonResponse({
        "id": inc.id,
        "title": inc.title,
        "severity": inc.severity,
        "status": inc.status,
        "scope": inc.scope,
        "tenant_id": inc.tenant_id,
        "tenant_slug": inc.tenant_slug,
        "root_cause_summary": inc.root_cause_summary,
        "suggested_actions": inc.suggested_actions,
        "created_at": inc.created_at.isoformat(),
        "updated_at": inc.updated_at.isoformat(),
        "resolved_at": inc.resolved_at.isoformat() if inc.resolved_at else None,
        "remediation_logs": logs,
    })


def _get_post_data(request):
    """Get POST data from form or JSON body."""
    if request.content_type and "application/json" in request.content_type:
        import json
        try:
            return json.loads(request.body) if request.body else {}
        except json.JSONDecodeError:
            return {}
    return request.POST


@require_POST
@_staff_api
def incident_remediate(request, incident_id):
    """Run remediation for an incident (single action or all suggested)."""
    data = _get_post_data(request)
    inc = get_object_or_404(Incident, pk=incident_id)
    action_code = data.get("action_code")
    run_all = data.get("run_all") in (True, "1", "true", "yes")
    approved = data.get("approved") in (True, "1", "true", "yes")
    runner = RemediationRunner()
    if run_all:
        logs = runner.run_suggested_actions(incident_id, approved=approved)
        result = [{"id": l.id, "action_code": l.action_code, "status": l.status, "message": l.message} for l in logs]
        return JsonResponse({"remediation_logs": result})
    if not action_code:
        return JsonResponse({"error": "action_code or run_all required"}, status=400)
    tenant_id = data.get("tenant_id")
    tenant_slug = data.get("tenant_slug")
    log = runner.run_action(
        incident_id,
        action_code,
        approved=approved,
        tenant_id=int(tenant_id) if tenant_id else None,
        tenant_slug=tenant_slug or None,
    )
    return JsonResponse({
        "id": log.id,
        "action_code": log.action_code,
        "status": log.status,
        "message": log.message,
    })


@require_GET
@_staff_api
def remediation_logs_list(request):
    """List remediation logs with optional filters."""
    qs = RemediationLog.objects.all().select_related("incident").order_by("-started_at")[:200]
    incident_id = request.GET.get("incident_id")
    if incident_id:
        qs = qs.filter(incident_id=incident_id)
    action_code = request.GET.get("action_code")
    if action_code:
        qs = qs.filter(action_code=action_code)
    logs = [
        {
            "id": l.id,
            "incident_id": l.incident_id,
            "action_code": l.action_code,
            "status": l.status,
            "started_at": l.started_at.isoformat(),
            "finished_at": l.finished_at.isoformat() if l.finished_at else None,
            "message": l.message,
        }
        for l in qs
    ]
    return JsonResponse({"results": logs, "count": len(logs)})


@require_POST
@_staff_api
def scan_view(request):
    """
    Run a manual diagnostic scan (targeted).
    Body: scope (platform|tenant|database|api|service), tenant_id?, service?, apply_fixes? (bool).
    """
    data = _get_post_data(request)
    scope = (data.get("scope") or "").strip().lower()
    if scope not in ("platform", "tenant", "database", "api", "service"):
        return JsonResponse({"error": "scope required: platform, tenant, database, api, or service"}, status=400)
    tenant_id = data.get("tenant_id")
    if tenant_id is not None:
        try:
            tenant_id = int(tenant_id)
        except (TypeError, ValueError):
            tenant_id = None
    if scope == "tenant" and not tenant_id:
        return JsonResponse({"error": "tenant_id required for scope=tenant"}, status=400)
    service = (data.get("service") or "").strip() or None
    if scope == "service" and not service:
        return JsonResponse({"error": "service required for scope=service (e.g. cache, default_db, app_registry)"}, status=400)
    apply_fixes = data.get("apply_fixes") in (True, "1", "true", "yes")
    try:
        report = run_manual_scan(scope=scope, tenant_id=tenant_id, service=service, apply_fixes=apply_fixes)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    return JsonResponse(_report_payload(report))


@require_GET
@_staff_api
def reports_list(request):
    """List diagnostic reports with optional filters."""
    qs = DiagnosticReport.objects.all().order_by("-created_at")[:200]
    trigger = request.GET.get("trigger")
    if trigger:
        qs = qs.filter(trigger=trigger)
    date_from = request.GET.get("date_from")
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    date_to = request.GET.get("date_to")
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    results = []
    for r in qs:
        results.append({
            "id": r.id,
            "trigger": r.trigger,
            "target": r.target,
            "status": r.status,
            "started_at": r.started_at.isoformat(),
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "summary": r.summary,
            "created_at": r.created_at.isoformat(),
        })
    return JsonResponse({"results": results, "count": len(results)})


@require_GET
@_staff_api
def report_detail(request, report_id):
    """Single diagnostic report with check runs, findings, incidents, remediation logs."""
    report = get_object_or_404(DiagnosticReport, pk=report_id)
    runs = []
    for run in report.check_runs.all():
        runs.append({
            "id": run.id,
            "scope": run.scope,
            "tenant_slug": run.tenant_slug,
            "check_type": run.check_type,
            "status": run.status,
            "message": run.message,
            "duration_ms": run.duration_ms,
            "created_at": run.created_at.isoformat(),
        })
    findings = []
    for run in report.check_runs.all():
        for f in run.findings.all():
            findings.append({
                "id": f.id,
                "run_id": f.run_id,
                "code": f.code,
                "title": f.title,
                "severity": f.severity,
                "details": f.details,
                "tenant_id": f.tenant_id,
            })
    incidents = []
    for inc in report.incidents.all():
        logs = [{"action_code": l.action_code, "status": l.status, "message": l.message} for l in inc.remediation_logs.all()]
        incidents.append({
            "id": inc.id,
            "title": inc.title,
            "severity": inc.severity,
            "status": inc.status,
            "root_cause_summary": inc.root_cause_summary,
            "suggested_actions": inc.suggested_actions,
            "remediation_logs": logs,
        })
    return JsonResponse(_report_payload(report, runs=runs, findings=findings, incidents=incidents))


def _report_payload(report, runs=None, findings=None, incidents=None):
    payload = {
        "id": report.id,
        "trigger": report.trigger,
        "target": report.target,
        "status": report.status,
        "started_at": report.started_at.isoformat(),
        "finished_at": report.finished_at.isoformat() if report.finished_at else None,
        "summary": report.summary,
        "error_message": report.error_message or "",
        "created_at": report.created_at.isoformat(),
    }
    if runs is not None:
        payload["check_runs"] = runs
    if findings is not None:
        payload["findings"] = findings
    if incidents is not None:
        payload["incidents"] = incidents
    return payload
