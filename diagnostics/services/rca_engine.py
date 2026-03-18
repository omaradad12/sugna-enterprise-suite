"""
Root cause analysis engine: correlate findings and set root_cause_summary + suggested_actions on incidents.
"""
from __future__ import annotations

from django.utils import timezone

from diagnostics.models import DiagnosticReport, Finding, Incident


class RCAEngine:
    """Rule-based RCA: map finding codes to root cause text and suggested remediation actions."""

    # Map finding code -> (root_cause_summary, suggested_actions)
    RULES = {
        "DEFAULT_DB_DOWN": (
            "Default (platform) database is unreachable. Check PostgreSQL, network, and credentials.",
            ["reconnect_default_db", "clear_django_cache"],
        ),
        "APP_REGISTRY_ERROR": (
            "Django app registry failed (e.g. missing module or import error).",
            [],
        ),
        "TENANT_DB_DOWN": (
            "Tenant database is unreachable. Check tenant DB host, credentials, and network.",
            ["reconnect_tenant_db", "warm_tenant_connections"],
        ),
        "CACHE_ERROR": (
            "Cache backend unreachable or get/set failed.",
            ["clear_django_cache"],
        ),
        "API_HEALTH_FAIL": (
            "API health endpoint returned non-2xx or was unreachable.",
            [],
        ),
    }

    def __init__(self, using: str = "default"):
        self.using = using

    def run_for_finding(self, finding: Finding, report: DiagnosticReport | None = None) -> Incident | None:
        """Create or update an incident from a high-severity finding and run RCA."""
        if finding.severity not in (Finding.Severity.CRITICAL, Finding.Severity.HIGH):
            return None
        summary, actions = self.RULES.get(
            finding.code, ("Unknown cause.", [])
        )
        # For manual report: always create new incident so report.incidents reflects this scan
        if not report:
            # Deduplicate: reuse open incident for same scope/tenant/code within last 24h
            qs = Incident.objects.using(self.using).filter(
                status=Incident.Status.OPEN,
                created_at__gte=timezone.now() - timezone.timedelta(hours=24),
            )
            if finding.tenant_id:
                qs = qs.filter(tenant_id=finding.tenant_id)
            else:
                qs = qs.filter(tenant_id__isnull=True)
            existing = qs.filter(title=finding.title).first()
        else:
            existing = None
        if existing:
            existing.root_cause_summary = summary
            existing.suggested_actions = actions
            existing.updated_at = timezone.now()
            existing.save(using=self.using, update_fields=["root_cause_summary", "suggested_actions", "updated_at"])
            return existing
        incident = Incident.objects.using(self.using).create(
            title=finding.title,
            severity=finding.severity,
            status=Incident.Status.OPEN,
            scope=Incident.Scope.TENANT if finding.tenant_id else Incident.Scope.PLATFORM,
            tenant_id=finding.tenant_id,
            tenant_slug=finding.details.get("tenant_slug", "") if finding.details else "",
            report=report,
            root_cause_summary=summary,
            suggested_actions=actions,
        )
        return incident

    def run_for_open_incidents(self) -> list[Incident]:
        """Re-run RCA for open incidents (e.g. refresh suggested_actions from latest findings)."""
        updated = []
        for incident in Incident.objects.using(self.using).filter(
            status__in=(Incident.Status.OPEN, Incident.Status.INVESTIGATING)
        ):
            # Find latest related finding by tenant/scope
            qs = Finding.objects.using(self.using).filter(
                severity__in=(Finding.Severity.CRITICAL, Finding.Severity.HIGH)
            ).order_by("-created_at")
            if incident.tenant_id:
                qs = qs.filter(tenant_id=incident.tenant_id)
            else:
                qs = qs.filter(tenant_id__isnull=True)
            finding = qs.first()
            if finding and finding.code in self.RULES:
                summary, actions = self.RULES[finding.code]
                incident.root_cause_summary = summary
                incident.suggested_actions = actions
                incident.updated_at = timezone.now()
                incident.save(using=self.using, update_fields=["root_cause_summary", "suggested_actions", "updated_at"])
                updated.append(incident)
        return updated
