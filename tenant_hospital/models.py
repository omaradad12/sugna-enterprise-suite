from __future__ import annotations

from decimal import Decimal

from django.core.validators import RegexValidator
from django.db import models


class Department(models.Model):
    code = models.CharField(max_length=20, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class Provider(models.Model):
    class ProviderType(models.TextChoices):
        PHYSICIAN = "physician", "Physician"
        NURSE = "nurse", "Nurse"
        LAB = "lab", "Lab"
        PHARMACY = "pharmacy", "Pharmacy"
        OTHER = "other", "Other"

    full_name = models.CharField(max_length=160, db_index=True)
    provider_type = models.CharField(max_length=20, choices=ProviderType.choices, default=ProviderType.PHYSICIAN)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, null=True, blank=True, related_name="providers")
    license_number = models.CharField(max_length=80, blank=True, db_index=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["full_name", "id"]

    def __str__(self) -> str:
        return self.full_name


_mrn_validator = RegexValidator(
    regex=r"^[A-Z0-9\-]+$",
    message="MRN may only contain letters, numbers, and hyphen.",
)


class Patient(models.Model):
    """
    Single master demographic record. Visit type (OPD/IPD/ER) is never stored here—only on encounters/visits.
    """

    class Gender(models.TextChoices):
        FEMALE = "female", "Female"
        MALE = "male", "Male"
        OTHER = "other", "Other"
        UNKNOWN = "unknown", "Unknown"

    mrn = models.CharField(
        max_length=40,
        unique=True,
        db_index=True,
        validators=[_mrn_validator],
        help_text="Medical Record Number (tenant-scoped unique).",
    )
    full_name = models.CharField(max_length=160, db_index=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, default=Gender.UNKNOWN, db_index=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    emergency_contact_name = models.CharField(
        max_length=160, blank=True, help_text="Next of kin or emergency contact name."
    )
    emergency_contact_phone = models.CharField(max_length=50, blank=True)
    allergies = models.TextField(blank=True, help_text="Known allergies and adverse reactions.")
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name", "mrn"]
        indexes = [
            models.Index(fields=["full_name", "date_of_birth"]),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.mrn})"


class PatientDocument(models.Model):
    """Attachment stored against the patient master (reports, consents, ID copies, etc.)."""

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to="hospital/patient_docs/%Y/%m/", max_length=255)
    notes = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-uploaded_at", "id"]

    def __str__(self) -> str:
        return f"{self.patient.mrn} — {self.title}"


class Appointment(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        CHECKED_IN = "checked_in", "Checked in"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        NO_SHOW = "no_show", "No show"

    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="appointments")
    provider = models.ForeignKey(Provider, on_delete=models.PROTECT, null=True, blank=True, related_name="appointments")
    department = models.ForeignKey(Department, on_delete=models.PROTECT, null=True, blank=True, related_name="appointments")

    start_at = models.DateTimeField(db_index=True)
    end_at = models.DateTimeField(db_index=True)
    reason = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED, db_index=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_at", "id"]
        indexes = [
            models.Index(fields=["status", "start_at"]),
            models.Index(fields=["patient", "start_at"]),
        ]

    def __str__(self) -> str:
        return f"Appt {self.patient.mrn} {self.start_at:%Y-%m-%d %H:%M}"


class Encounter(models.Model):
    """
    A clinical encounter (visit) linked to exactly one patient master.
    visit_kind separates OPD / IPD / emergency; type-specific fields live in related detail rows.
    """

    class VisitKind(models.TextChoices):
        OPD = "opd", "Outpatient (OPD)"
        IPD = "ipd", "Inpatient (IPD)"
        EMERGENCY = "emergency", "Emergency"
        UNSPECIFIED = "unspecified", "Unspecified"

    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="encounters")
    provider = models.ForeignKey(Provider, on_delete=models.PROTECT, null=True, blank=True, related_name="encounters")
    appointment = models.OneToOneField(Appointment, on_delete=models.SET_NULL, null=True, blank=True, related_name="encounter")
    visit_kind = models.CharField(
        max_length=20,
        choices=VisitKind.choices,
        default=VisitKind.UNSPECIFIED,
        db_index=True,
        help_text="Set by workflow: OPD, IPD, or emergency—not stored on Patient.",
    )
    started_at = models.DateTimeField(db_index=True)
    ended_at = models.DateTimeField(null=True, blank=True, db_index=True)
    chief_complaint = models.CharField(max_length=255, blank=True)
    summary = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-started_at", "id"]
        indexes = [
            models.Index(fields=["patient", "started_at"]),
            models.Index(fields=["visit_kind", "started_at"]),
        ]

    def __str__(self) -> str:
        return f"Encounter {self.patient.mrn} {self.get_visit_kind_display()} {self.started_at:%Y-%m-%d}"


class OutpatientVisit(models.Model):
    """OPD visit detail; one per outpatient encounter."""

    encounter = models.OneToOneField(Encounter, on_delete=models.CASCADE, related_name="opd_detail")
    visit_date = models.DateField(db_index=True)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, null=True, blank=True, related_name="opd_visits")
    doctor = models.ForeignKey(Provider, on_delete=models.PROTECT, null=True, blank=True, related_name="opd_visits")
    symptoms = models.TextField(blank=True)
    diagnosis = models.TextField(blank=True)
    prescription = models.TextField(blank=True)
    follow_up_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-visit_date", "id"]

    def __str__(self) -> str:
        return f"OPD {self.encounter.patient.mrn} {self.visit_date}"


class EmergencyVisit(models.Model):
    """Emergency visit detail; one per emergency encounter."""

    class Outcome(models.TextChoices):
        DISCHARGE = "discharge", "Discharge"
        ADMIT = "admit", "Admit"
        REFER = "refer", "Refer"

    encounter = models.OneToOneField(Encounter, on_delete=models.CASCADE, related_name="emergency_detail")
    triage_level = models.CharField(max_length=40, blank=True, help_text="e.g. ESI level or local triage code.")
    emergency_notes = models.TextField(blank=True)
    outcome = models.CharField(max_length=20, choices=Outcome.choices, default=Outcome.DISCHARGE, db_index=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"ER {self.encounter.patient.mrn} {self.encounter.started_at:%Y-%m-%d %H:%M}"


# --- EMR: vitals & notes ---


class VitalSign(models.Model):
    """One set of vitals captured during an encounter."""

    encounter = models.ForeignKey(Encounter, on_delete=models.CASCADE, related_name="vital_signs")
    recorded_at = models.DateTimeField(db_index=True)
    bp_systolic = models.PositiveSmallIntegerField(null=True, blank=True)
    bp_diastolic = models.PositiveSmallIntegerField(null=True, blank=True)
    heart_rate = models.PositiveSmallIntegerField(null=True, blank=True, help_text="bpm")
    temperature_c = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    spo2 = models.PositiveSmallIntegerField(null=True, blank=True, help_text="%")
    respiratory_rate = models.PositiveSmallIntegerField(null=True, blank=True)
    weight_kg = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    height_cm = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-recorded_at", "id"]


class ClinicalNote(models.Model):
    class NoteType(models.TextChoices):
        PROGRESS = "progress", "Progress"
        SOAP_S = "soap_s", "SOAP — Subjective"
        SOAP_O = "soap_o", "SOAP — Objective"
        SOAP_A = "soap_a", "SOAP — Assessment"
        SOAP_P = "soap_p", "SOAP — Plan"
        OTHER = "other", "Other"

    encounter = models.ForeignKey(Encounter, on_delete=models.CASCADE, related_name="clinical_notes")
    author_provider = models.ForeignKey(Provider, on_delete=models.SET_NULL, null=True, blank=True, related_name="authored_notes")
    note_type = models.CharField(max_length=20, choices=NoteType.choices, default=NoteType.PROGRESS)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "id"]


# --- Lab & pharmacy orders ---


class LabOrder(models.Model):
    class Status(models.TextChoices):
        ORDERED = "ordered", "Ordered"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    order_number = models.CharField(max_length=32, unique=True, db_index=True)
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="lab_orders")
    encounter = models.ForeignKey(Encounter, on_delete=models.SET_NULL, null=True, blank=True, related_name="lab_orders")
    ordered_by = models.ForeignKey(Provider, on_delete=models.SET_NULL, null=True, blank=True, related_name="lab_orders_ordered")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ORDERED, db_index=True)
    ordered_at = models.DateTimeField(db_index=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-ordered_at", "id"]


class LabOrderLine(models.Model):
    class LineStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        RESULTED = "resulted", "Resulted"
        CANCELLED = "cancelled", "Cancelled"

    lab_order = models.ForeignKey(LabOrder, on_delete=models.CASCADE, related_name="lines")
    test_code = models.CharField(max_length=40, blank=True, db_index=True)
    test_name = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=LineStatus.choices, default=LineStatus.PENDING)
    result_text = models.TextField(blank=True)
    resulted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]


class PharmacyOrder(models.Model):
    class Status(models.TextChoices):
        ORDERED = "ordered", "Ordered"
        DISPENSED = "dispensed", "Dispensed"
        CANCELLED = "cancelled", "Cancelled"

    order_number = models.CharField(max_length=32, unique=True, db_index=True)
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="pharmacy_orders")
    encounter = models.ForeignKey(Encounter, on_delete=models.SET_NULL, null=True, blank=True, related_name="pharmacy_orders")
    ordered_by = models.ForeignKey(Provider, on_delete=models.SET_NULL, null=True, blank=True, related_name="pharmacy_orders_ordered")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ORDERED, db_index=True)
    ordered_at = models.DateTimeField(db_index=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-ordered_at", "id"]


class PharmacyOrderLine(models.Model):
    pharmacy_order = models.ForeignKey(PharmacyOrder, on_delete=models.CASCADE, related_name="lines")
    medication_name = models.CharField(max_length=200)
    dose = models.CharField(max_length=120, blank=True)
    route = models.CharField(max_length=80, blank=True, help_text="e.g. PO, IV")
    frequency = models.CharField(max_length=120, blank=True)
    quantity = models.CharField(max_length=80, blank=True)
    instructions = models.TextField(blank=True)

    class Meta:
        ordering = ["id"]


# --- Inpatient: wards, beds, admissions ---


class Ward(models.Model):
    code = models.CharField(max_length=20, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    floor = models.CharField(max_length=40, blank=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="wards")
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class Bed(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        OCCUPIED = "occupied", "Occupied"
        MAINTENANCE = "maintenance", "Maintenance"

    ward = models.ForeignKey(Ward, on_delete=models.CASCADE, related_name="beds")
    room_label = models.CharField(max_length=40, blank=True)
    bed_label = models.CharField(max_length=40, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE, db_index=True)

    class Meta:
        ordering = ["ward", "room_label", "bed_label"]
        constraints = [
            models.UniqueConstraint(fields=["ward", "room_label", "bed_label"], name="uniq_tenant_hospital_bed_room"),
        ]

    def __str__(self) -> str:
        return f"{self.ward.code} {self.room_label}-{self.bed_label}"


class Admission(models.Model):
    """
    Inpatient stay for an existing patient master. Links optionally to an IPD Encounter for clinical context.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DISCHARGED = "discharged", "Discharged"

    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="admissions")
    encounter = models.OneToOneField(
        Encounter,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admission",
        help_text="IPD encounter for this admission (created at admit time).",
    )
    bed = models.ForeignKey(Bed, on_delete=models.PROTECT, related_name="admissions")
    attending_provider = models.ForeignKey(
        Provider,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admissions_attending",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    admitted_at = models.DateTimeField(db_index=True)
    discharged_at = models.DateTimeField(null=True, blank=True, db_index=True)
    chief_complaint = models.CharField(max_length=255, blank=True)
    admission_diagnosis = models.TextField(blank=True)
    discharge_summary = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-admitted_at", "id"]
        indexes = [
            models.Index(fields=["status", "admitted_at"]),
        ]


# --- Billing & insurance ---


class InsurancePlan(models.Model):
    code = models.CharField(max_length=40, unique=True, db_index=True)
    name = models.CharField(max_length=160)
    payer_name = models.CharField(max_length=160, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class PatientInsurance(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="insurance_policies")
    plan = models.ForeignKey(InsurancePlan, on_delete=models.PROTECT, related_name="patient_policies")
    policy_number = models.CharField(max_length=80, db_index=True)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    is_primary = models.BooleanField(default=True, db_index=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-is_primary", "id"]


class PatientInvoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"
        PARTIAL = "partial", "Partially paid"
        PAID = "paid", "Paid"
        VOID = "void", "Void"

    invoice_number = models.CharField(max_length=32, unique=True, db_index=True)
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name="invoices")
    encounter = models.ForeignKey(Encounter, on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="USD", db_index=True)
    issued_at = models.DateTimeField(db_index=True)
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-issued_at", "id"]

