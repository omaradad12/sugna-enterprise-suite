"""
Remediation runner: execute allowed actions and log to RemediationLog.
"""
from __future__ import annotations

from django.utils import timezone
from django.db import connections
from django.core.management import call_command

from diagnostics.models import Incident, RemediationLog, RemediationPolicy
from tenants.db import ensure_tenant_db_configured, tenant_db_alias
from tenants.models import Tenant


class RemediationRunner:
    """Execute remediation actions and respect RemediationPolicy."""

    def __init__(self, using: str = "default"):
        self.using = using

    def is_allowed(self, action_code: str, require_approval: bool = False) -> bool:
        """Check policy: allowed and (if require_approval) must be explicitly approved."""
        try:
            policy = RemediationPolicy.objects.using(self.using).get(action_code=action_code)
            if not policy.allowed:
                return False
            if require_approval and policy.require_approval:
                return False  # Caller can pass approval flag to bypass
            return True
        except RemediationPolicy.DoesNotExist:
            return self._default_allowed(action_code)

    def _default_allowed(self, action_code: str) -> bool:
        """Defaults for known safe actions."""
        safe = {
            "reconnect_default_db",
            "clear_django_cache",
            "warm_tenant_connections",
            "reconnect_tenant_db",
            "run_tenant_migrations",
            "mark_tenant_maintenance",
        }
        return action_code in safe

    def run_action(
        self,
        incident_id: int,
        action_code: str,
        *,
        approved: bool = False,
        tenant_id: int | None = None,
        tenant_slug: str | None = None,
    ) -> RemediationLog:
        """Execute one remediation action for an incident and log result."""
        incident = Incident.objects.using(self.using).get(pk=incident_id)
        if not self.is_allowed(action_code, require_approval=not approved):
            log = RemediationLog.objects.using(self.using).create(
                incident=incident,
                action_code=action_code,
                status=RemediationLog.Status.SKIPPED,
                message="Action not allowed by policy or requires approval.",
            )
            return log

        started = timezone.now()
        log = RemediationLog.objects.using(self.using).create(
            incident=incident,
            action_code=action_code,
            status=RemediationLog.Status.SUCCESS,
            message="",
        )
        try:
            if action_code == "reconnect_default_db":
                self._reconnect_default_db()
            elif action_code == "clear_django_cache":
                self._clear_django_cache()
            elif action_code == "warm_tenant_connections":
                self._warm_tenant_connections()
            elif action_code == "reconnect_tenant_db":
                tid = tenant_id or incident.tenant_id
                if not tid:
                    raise ValueError("tenant_id required for reconnect_tenant_db")
                self._reconnect_tenant_db(tid)
            elif action_code == "run_tenant_migrations":
                slug = tenant_slug or incident.tenant_slug
                if not slug:
                    raise ValueError("tenant_slug required for run_tenant_migrations")
                self._run_tenant_migrations(slug)
            elif action_code == "mark_tenant_maintenance":
                tid = tenant_id or incident.tenant_id
                if not tid:
                    raise ValueError("tenant_id required for mark_tenant_maintenance")
                self._mark_tenant_maintenance(tid)
            else:
                log.status = RemediationLog.Status.SKIPPED
                log.message = f"Unknown action: {action_code}"
                log.finished_at = timezone.now()
                log.save(using=self.using, update_fields=["status", "message", "finished_at"])
                return log
            log.message = "Completed successfully."
            log.finished_at = timezone.now()
            log.save(using=self.using, update_fields=["message", "finished_at"])
        except Exception as e:
            log.status = RemediationLog.Status.FAILURE
            log.message = str(e)[:500]
            log.finished_at = timezone.now()
            log.save(using=self.using, update_fields=["status", "message", "finished_at"])
        return log

    def _reconnect_default_db(self) -> None:
        connections["default"].close()

    def _clear_django_cache(self) -> None:
        from django.core.cache import cache
        cache.clear()

    def _warm_tenant_connections(self) -> None:
        for tenant in Tenant.objects.using(self.using).filter(db_name__isnull=False).exclude(db_name=""):
            alias = ensure_tenant_db_configured(tenant)
            conn = connections[alias]
            conn.ensure_connection()
            conn.cursor().execute("SELECT 1")

    def _reconnect_tenant_db(self, tenant_id: int) -> None:
        tenant = Tenant.objects.using(self.using).get(pk=tenant_id)
        alias = tenant_db_alias(tenant)
        if alias in connections:
            connections[alias].close()
        ensure_tenant_db_configured(tenant)
        connections[alias].ensure_connection()
        connections[alias].cursor().execute("SELECT 1")

    def _run_tenant_migrations(self, tenant_slug: str) -> None:
        tenant = Tenant.objects.using(self.using).get(slug=tenant_slug)
        ensure_tenant_db_configured(tenant)
        alias = tenant_db_alias(tenant)
        call_command("migrate", database=alias, interactive=False)

    def _mark_tenant_maintenance(self, tenant_id: int) -> None:
        # No-op: no Tenant.maintenance_mode field yet; avoid changing is_active.
        pass

    def run_suggested_actions(self, incident_id: int, *, approved: bool = False) -> list[RemediationLog]:
        """Run all suggested actions for an incident that are allowed."""
        incident = Incident.objects.using(self.using).get(pk=incident_id)
        logs = []
        for action_code in incident.suggested_actions or []:
            log = self.run_action(
                incident_id,
                action_code,
                approved=approved,
                tenant_id=incident.tenant_id,
                tenant_slug=incident.tenant_slug or None,
            )
            logs.append(log)
        return logs
