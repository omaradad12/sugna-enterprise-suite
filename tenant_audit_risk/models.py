"""
Audit & Risk Management models: risk assessments, alerts, investigations, controls.
All models are tenant-scoped (stored in tenant DB).
Uses source_type string (e.g. 'journalentry') + source_id to avoid ContentType in tenant DB.
"""
from decimal import Decimal

from django.db import models


class TransactionRiskAssessment(models.Model):
    """
    Fraud/risk assessment for a single transaction (journal entry, payment, invoice, etc.).
    One assessment per transaction; updated when engine re-runs.
    """

    class RiskLevel(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    source_type = models.CharField(max_length=80, db_index=True)  # e.g. "journalentry", "supplierinvoice"
    source_id = models.PositiveIntegerField(db_index=True)

    risk_score = models.PositiveSmallIntegerField(default=0)  # 0-100
    risk_level = models.CharField(
        max_length=20, choices=RiskLevel.choices, default=RiskLevel.LOW, db_index=True
    )
    assessed_at = models.DateTimeField(auto_now=True)
    details = models.JSONField(
        default=dict,
        blank=True,
        help_text="Which indicators fired: {indicator_code: points, ...}",
    )
    indicator_summary = models.CharField(max_length=500, blank=True)

    # Risk investigation register
    class InvestigationStatus(models.TextChoices):
        DETECTED = "detected", "Detected"
        UNDER_REVIEW = "under_review", "Under review"
        CLEARED = "cleared", "Cleared"
        CORRECTION_REQUESTED = "correction_requested", "Correction requested"
        CONVERTED_TO_FINDING = "converted_to_finding", "Converted to finding"
        CLOSED = "closed", "Closed"

    investigation_status = models.CharField(
        max_length=24,
        choices=InvestigationStatus.choices,
        default=InvestigationStatus.DETECTED,
        db_index=True,
    )
    assigned_to_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    module = models.CharField(max_length=80, blank=True)
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
    )
    grant = models.ForeignKey(
        "tenant_grants.Grant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="risk_assessments",
    )
    vendor_display = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-assessed_at"]
        indexes = [
            models.Index(fields=["source_type", "source_id"]),
            models.Index(fields=["risk_level"]),
            models.Index(fields=["-assessed_at"]),
            models.Index(fields=["investigation_status"]),
        ]
        unique_together = [("source_type", "source_id")]

    def __str__(self):
        return f"Risk {self.risk_level} ({self.risk_score}) for {self.source_type}#{self.source_id}"


class RiskAlert(models.Model):
    """
    Alert created when a transaction exceeds risk threshold or a control is violated.
    """

    class AlertType(models.TextChoices):
        FRAUD = "fraud", "Fraud"
        CONTROL_VIOLATION = "control_violation", "Control Violation"
        DUPLICATE_PAYMENT = "duplicate_payment", "Duplicate Payment"
        BACKDATED = "backdated", "Backdated Entry"
        BUDGET_VIOLATION = "budget_violation", "Budget Violation"
        SEGREGATION_VIOLATION = "segregation_violation", "Segregation of Duties"
        VENDOR_RISK = "vendor_risk", "Vendor Risk"
        UNUSUAL_ACTIVITY = "unusual_activity", "Unusual Activity"
        OTHER = "other", "Other"

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        CLOSED = "closed", "Closed"

    assessment = models.ForeignKey(
        TransactionRiskAssessment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alerts",
    )
    alert_type = models.CharField(max_length=40, choices=AlertType.choices, db_index=True)
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.MEDIUM)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_by_user_id = models.PositiveIntegerField(null=True, blank=True)
    investigation = models.ForeignKey(
        "InvestigationCase",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alerts",
    )

    # Control violation register fields (used when alert_type=control_violation)
    class ViolationStatus(models.TextChoices):
        OPEN = "open", "Open"
        UNDER_REVIEW = "under_review", "Under review"
        CORRECTION_REQUESTED = "correction_requested", "Correction requested"
        CORRECTED = "corrected", "Corrected"
        REVALIDATED = "revalidated", "Revalidated"
        CLOSED = "closed", "Closed"

    violation_status = models.CharField(
        max_length=24,
        choices=ViolationStatus.choices,
        null=True,
        blank=True,
        db_index=True,
        help_text="Workflow status for control violations.",
    )
    control_rule = models.ForeignKey(
        "ControlRule",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="violations",
    )
    module = models.CharField(max_length=80, blank=True, help_text="Module e.g. Finance, Procurement.")
    amount_affected = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    assigned_to_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    grant = models.ForeignKey(
        "tenant_grants.Grant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="control_violation_alerts",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["alert_type"]),
            models.Index(fields=["violation_status"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"


class InvestigationCase(models.Model):
    """
    Case opened for investigating fraud or control breach; can link alerts and evidence.
    """

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In Progress"
        CLOSED = "closed", "Closed"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    title = models.CharField(max_length=200)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True
    )
    priority = models.CharField(
        max_length=20, choices=Priority.choices, default=Priority.MEDIUM
    )
    assigned_to_id = models.PositiveIntegerField(null=True, blank=True)
    summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"


class InvestigationNote(models.Model):
    """Investigator notes on a case."""
    case = models.ForeignKey(
        InvestigationCase, on_delete=models.CASCADE, related_name="notes"
    )
    author_user_id = models.PositiveIntegerField(null=True, blank=True)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class InvestigationAttachment(models.Model):
    """Evidence attachment for an investigation case."""
    case = models.ForeignKey(
        InvestigationCase, on_delete=models.CASCADE, related_name="attachments"
    )
    file = models.FileField(upload_to="audit_risk/evidence/%Y/%m/")
    original_filename = models.CharField(max_length=255, blank=True)
    description = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]


class ControlRule(models.Model):
    """
    Configurable control rule for compliance (approval threshold, segregation, etc.).
    """

    class RuleType(models.TextChoices):
        APPROVAL_THRESHOLD = "approval_threshold", "Approval Threshold"
        SEGREGATION_OF_DUTIES = "segregation_of_duties", "Segregation of Duties"
        BUDGET_CHECK = "budget_check", "Budget Check"
        DOCUMENT_REQUIRED = "document_required", "Document Required"
        CUSTOM = "custom", "Custom"

    name = models.CharField(max_length=120)
    rule_type = models.CharField(max_length=40, choices=RuleType.choices)
    config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_rule_type_display()})"


class AuditFinding(models.Model):
    """
    Audit finding with full lifecycle: system alert → preliminary → confirmed → realized
    → correction/revalidation → recovery → closure.
    """

    class FindingStage(models.TextChoices):
        PRELIMINARY = "preliminary", "Preliminary"
        CONFIRMED = "confirmed", "Confirmed"
        REALIZED = "realized", "Realized"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In Progress"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    class RecoveryStatus(models.TextChoices):
        NOT_STARTED = "not_started", "Not started"
        IN_PROGRESS = "in_progress", "In progress"
        PARTIAL = "partial", "Partially recovered"
        RECOVERED = "recovered", "Recovered"
        WRITTEN_OFF = "written_off", "Written off"
        N_A = "n_a", "N/A"

    # Link to source system alert (optional)
    alert = models.ForeignKey(
        RiskAlert,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="findings",
    )
    finding_stage = models.CharField(
        max_length=20,
        choices=FindingStage.choices,
        default=FindingStage.PRELIMINARY,
        db_index=True,
        help_text="Preliminary (under review), Confirmed (validated), Realized (impact materialized).",
    )
    is_actual = models.BooleanField(
        default=False,
        help_text="Whether the finding is an actual finding (true) or a false positive.",
    )
    is_realized = models.BooleanField(
        default=False,
        help_text="Whether financial or other impact has been realized.",
    )

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True
    )
    recommendation = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    assigned_to_id = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    realized_at = models.DateTimeField(null=True, blank=True)

    # Impact and recovery (for confirmed/realized findings)
    financial_impact = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, default=0
    )
    recovered_amount = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True, default=0
    )
    unrecovered_amount = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Outstanding exposure (financial_impact minus recovered).",
    )
    donor_project_impact = models.TextField(
        blank=True,
        help_text="Description of impact on donor(s) or project(s).",
    )
    root_cause = models.TextField(blank=True)
    management_action = models.TextField(
        blank=True,
        help_text="Actions taken or planned by management.",
    )
    recovery_status = models.CharField(
        max_length=20,
        choices=RecoveryStatus.choices,
        default=RecoveryStatus.NOT_STARTED,
        blank=True,
        db_index=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["finding_stage"]),
            models.Index(fields=["is_realized"]),
            models.Index(fields=["recovery_status"]),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.financial_impact is not None and self.recovered_amount is not None:
            fi = self.financial_impact
            rec = self.recovered_amount or Decimal("0")
            self.unrecovered_amount = max(Decimal("0"), (fi or Decimal("0")) - rec)
        super().save(*args, **kwargs)


class AuditCorrectionRequest(models.Model):
    """
    Correction request linked to a source transaction. Visible to the assigned user
    (creator of the source or assigned responsible user) for object-level access.
    Admin and Finance Manager can see all; data entry sees only requests assigned to them.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    finding = models.ForeignKey(
        AuditFinding,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="correction_requests",
    )
    source_type = models.CharField(max_length=80, db_index=True)  # e.g. journalentry, purchaserequisition
    source_id = models.PositiveIntegerField(db_index=True)
    assigned_to_id = models.PositiveIntegerField(db_index=True)  # TenantUser who must correct (creator or assigned)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    instructions = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by_id = models.PositiveIntegerField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    response_comment = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["assigned_to_id", "status"]),
        ]

    def __str__(self):
        return f"Correction request for {self.source_type}#{self.source_id} (assigned to {self.assigned_to_id})"


# ----- Audit Screening Upload (temporary storage only; files are never kept permanently) -----


class AuditScreeningSession(models.Model):
    """
    A screening session for external documents. Files are stored temporarily
    and are deleted when screening is finished, when the linked case is closed,
    or after SCREENING_UPLOAD_MAX_AGE_HOURS. Only metadata and screening
    results (summary, notes, risk flags) are kept.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        FINISHED = "finished", "Finished"
        CLOSED = "closed", "Closed"

    auditor_user_id = models.PositiveIntegerField(null=True, blank=True)
    case = models.ForeignKey(
        InvestigationCase,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="screening_sessions",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        help_text="Temp files are deleted after this time if not already finished."
    )
    finished_at = models.DateTimeField(null=True, blank=True)
    # What we keep after files are deleted:
    screening_summary = models.TextField(
        blank=True,
        help_text="Summary of screening results (kept; files are not).",
    )
    auditor_notes = models.TextField(
        blank=True,
        help_text="Auditor notes from the screening (kept).",
    )
    risk_flags = models.JSONField(
        default=list,
        blank=True,
        help_text="Detected risk indicators from screening (kept).",
    )
    transaction_references = models.JSONField(
        default=list,
        blank=True,
        help_text="References to transactions or items noted during screening.",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status"]), models.Index(fields=["expires_at"])]

    def __str__(self):
        return f"Screening session {self.id} ({self.get_status_display()})"


class ScreeningUploadFile(models.Model):
    """
    A file in temporary screening storage. The actual file lives under
    SCREENING_UPLOAD_TEMP_ROOT and must be deleted when the session
    is finished, closed, or expired. Only metadata is stored in DB.
    """

    session = models.ForeignKey(
        AuditScreeningSession,
        on_delete=models.CASCADE,
        related_name="uploaded_files",
    )
    # Relative path under screening temp root (session_id/filename)
    temp_file_path = models.CharField(max_length=500, db_index=True)
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(default=0)
    content_type = models.CharField(max_length=128, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at"]
