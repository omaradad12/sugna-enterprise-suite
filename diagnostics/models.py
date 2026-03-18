"""
Diagnostics models. All live in the default (platform) database.
"""
from django.db import models


class DiagnosticReport(models.Model):
    """Result of a manual or automatic diagnostic run; links runs, findings, incidents."""

    class Trigger(models.TextChoices):
        AUTOMATIC = "automatic", "Automatic"
        MANUAL = "manual", "Manual"

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    trigger = models.CharField(max_length=20, choices=Trigger.choices, default=Trigger.MANUAL, db_index=True)
    target = models.JSONField(default=dict, blank=True)  # scope, tenant_id?, service?
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING, db_index=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    summary = models.JSONField(default=dict, blank=True)  # total_checks, success_count, failure_count, incidents_created, remediations_applied
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Report {self.id} ({self.trigger}, {self.status})"


class DiagnosticCheckRun(models.Model):
    """Single run of platform or tenant checks."""

    class Scope(models.TextChoices):
        PLATFORM = "platform", "Platform"
        TENANT = "tenant", "Tenant"

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILURE = "failure", "Failure"
        TIMEOUT = "timeout", "Timeout"
        PARTIAL = "partial", "Partial"

    report = models.ForeignKey(
        DiagnosticReport,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="check_runs",
    )
    scope = models.CharField(max_length=20, choices=Scope.choices, db_index=True)
    tenant_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    tenant_slug = models.CharField(max_length=100, blank=True)
    check_type = models.CharField(max_length=80, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices)
    message = models.TextField(blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Diagnostic check run"
        verbose_name_plural = "Diagnostic check runs"

    def __str__(self):
        return f"{self.check_type} ({self.scope}) {self.created_at.isoformat()}"


class Finding(models.Model):
    """A single finding from a check run (e.g. DB down, migration pending)."""

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    run = models.ForeignKey(
        DiagnosticCheckRun,
        on_delete=models.CASCADE,
        related_name="findings",
        null=True,
        blank=True,
    )
    code = models.CharField(max_length=80, db_index=True)
    title = models.CharField(max_length=255)
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.MEDIUM)
    details = models.JSONField(default=dict, blank=True)
    tenant_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.code}: {self.title}"


class Incident(models.Model):
    """An incident (e.g. tenant DB down) with optional root cause and remediation."""

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        INVESTIGATING = "investigating", "Investigating"
        REMEDIATING = "remediating", "Remediating"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    class Scope(models.TextChoices):
        PLATFORM = "platform", "Platform"
        TENANT = "tenant", "Tenant"

    title = models.CharField(max_length=255)
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.MEDIUM)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    scope = models.CharField(max_length=20, choices=Scope.choices, default=Scope.PLATFORM)
    tenant_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    tenant_slug = models.CharField(max_length=100, blank=True)
    report = models.ForeignKey(
        DiagnosticReport,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incidents",
    )
    root_cause_summary = models.TextField(blank=True)
    suggested_actions = models.JSONField(default=list, blank=True)  # list of action codes
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.status})"


class RemediationLog(models.Model):
    """Log of an automated or manual remediation attempt."""

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILURE = "failure", "Failure"
        SKIPPED = "skipped", "Skipped"

    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="remediation_logs")
    action_code = models.CharField(max_length=80, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    message = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.action_code} ({self.status}) for incident {self.incident_id}"


class RemediationPolicy(models.Model):
    """Policy: which actions are allowed / require approval."""

    action_code = models.CharField(max_length=80, unique=True)
    allowed = models.BooleanField(default=True)
    require_approval = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Remediation policies"

    def __str__(self):
        return f"{self.action_code} (allowed={self.allowed})"


class LogEvent(models.Model):
    """Normalized log event for analysis (optional ingestion)."""

    source = models.CharField(max_length=80, db_index=True)
    level = models.CharField(max_length=20, db_index=True)
    message = models.TextField(blank=True)
    tenant_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    timestamp = models.DateTimeField(db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.source} [{self.level}] {self.timestamp.isoformat()}"
