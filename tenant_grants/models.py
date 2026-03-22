from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class ActiveDonorManager(models.Manager):
    """Return only active donors for grant/agreement/tracking dropdowns; inactive/archived remain for history."""

    def get_queryset(self):
        return super().get_queryset().filter(status="active")


class Donor(models.Model):
    """Master donor setup for NGO Financial & Grant Management. Code and name are unique; only active donors appear in grant/agreement dropdowns."""

    class DonorType(models.TextChoices):
        INSTITUTION = "institution", "Institution"
        GOVERNMENT = "government", "Government"
        PRIVATE = "private", "Private"
        FOUNDATION = "foundation", "Foundation"
        CORPORATE = "corporate", "Corporate"
        OTHER = "other", "Other"

    class DonorCategory(models.TextChoices):
        BILATERAL = "bilateral", "Bilateral"
        MULTILATERAL = "multilateral", "Multilateral"
        FOUNDATION = "foundation", "Foundation"
        CORPORATE = "corporate", "Corporate"
        NGO = "ngo", "NGO"
        INDIVIDUAL = "individual", "Individual"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        ARCHIVED = "archived", "Archived"

    # Same choices as DonorRestriction.RestrictionType for default flow into grants/reporting
    class DefaultRestrictionType(models.TextChoices):
        BUDGET_LINE = "budget_line", "Budget line restriction"
        PROCUREMENT = "procurement", "Procurement rules"
        REPORTING = "reporting", "Reporting requirement"
        OTHER = "other", "Other"

    # Same choices as ReportingRequirement.Frequency for default flow
    class DefaultReportingFrequency(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Quarterly"
        ANNUAL = "annual", "Annual"
        AD_HOC = "ad_hoc", "Ad hoc"

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200, unique=True)
    short_name = models.CharField(max_length=80, blank=True)
    donor_type = models.CharField(
        max_length=20, choices=DonorType.choices, default=DonorType.INSTITUTION, blank=True
    )
    donor_category = models.CharField(
        max_length=20, choices=DonorCategory.choices, default=DonorCategory.OTHER, blank=True
    )
    contact_person = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    country = models.CharField(max_length=100, blank=True)
    website = models.URLField(blank=True)
    preferred_currency = models.CharField(max_length=10, blank=True)
    default_restriction_type = models.CharField(
        max_length=20,
        choices=DefaultRestrictionType.choices,
        default=DefaultRestrictionType.OTHER,
        blank=True,
    )
    default_reporting_frequency = models.CharField(
        max_length=20,
        choices=DefaultReportingFrequency.choices,
        default=DefaultReportingFrequency.QUARTERLY,
        blank=True,
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    notes = models.TextField(blank=True)
    agreement_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    objects = models.Manager()
    active = ActiveDonorManager()

    class Meta:
        ordering = ["name"]
        verbose_name = "Donor (Register)"

    def __str__(self) -> str:
        return self.name


class FundingSource(models.Model):
    """Funding types (grants, donations, contributions) linked to donors and optionally projects."""

    class FundingType(models.TextChoices):
        GRANT = "grant", "Grant"
        DONATION = "donation", "Donation"
        CONTRIBUTION = "contribution", "Contribution"

    name = models.CharField(max_length=120)
    funding_type = models.CharField(
        max_length=20, choices=FundingType.choices, default=FundingType.GRANT
    )
    donor = models.ForeignKey(
        Donor, on_delete=models.PROTECT, related_name="funding_sources", null=True, blank=True
    )
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_funding_type_display()})"


class DonorAgreement(models.Model):
    """
    Signed donor agreements: contracts, funding limits, duration, compliance flags,
    and links to grants/projects for NGO ERP control and audit.
    """

    class AgreementType(models.TextChoices):
        GRANT = "grant", "Grant agreement"
        FRAMEWORK = "framework", "Framework agreement"
        PARTNERSHIP = "partnership", "Partnership agreement"
        CONTRIBUTION = "contribution", "Contribution agreement"
        MOU = "mou", "Memorandum of understanding"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        EXPIRED = "expired", "Expired"
        CLOSED = "closed", "Closed"

    class ReportingFrequency(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Quarterly"
        ANNUALLY = "annually", "Annually"

    agreement_code = models.CharField(
        max_length=40,
        unique=True,
        db_index=True,
        help_text="Unique reference (e.g. DAG-2025-00001).",
    )
    donor = models.ForeignKey(Donor, on_delete=models.CASCADE, related_name="agreements")
    title = models.CharField(max_length=200)
    agreement_type = models.CharField(
        max_length=30,
        choices=AgreementType.choices,
        default=AgreementType.GRANT,
        db_index=True,
    )
    reference_number = models.CharField(
        max_length=120,
        blank=True,
        help_text="Donor or legal reference number.",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    funding_source = models.ForeignKey(
        "FundingSource",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="donor_agreements",
    )
    currency = models.ForeignKey(
        "tenant_finance.Currency",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="donor_agreements",
    )
    funding_limit = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    payment_terms_summary = models.TextField(blank=True)
    installment_notes = models.TextField(blank=True)
    signed_date = models.DateField(null=True, blank=True, db_index=True)
    start_date = models.DateField(null=True, blank=True, db_index=True)
    end_date = models.DateField(null=True, blank=True, db_index=True)
    reporting_frequency = models.CharField(
        max_length=20,
        choices=ReportingFrequency.choices,
        blank=True,
    )
    compliance_financial_reporting = models.BooleanField(default=False)
    compliance_narrative_reporting = models.BooleanField(default=False)
    compliance_audit_required = models.BooleanField(default=False)
    compliance_special_conditions = models.BooleanField(default=False)
    restricted_funding = models.BooleanField(default=False)
    restriction_summary = models.TextField(blank=True)
    allow_multiple_grants = models.BooleanField(default=True)
    allow_multiple_projects = models.BooleanField(default=True)
    terms_summary = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)
    file = models.FileField(upload_to="grants/agreements/%Y/%m/", null=True, blank=True)
    original_filename = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-signed_date", "-created_at"]
        indexes = [
            models.Index(fields=["donor", "status"]),
            models.Index(fields=["signed_date"]),
            models.Index(fields=["start_date"]),
            models.Index(fields=["end_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.agreement_code}: {self.title}"

    def clean(self) -> None:
        from django.core.exceptions import ValidationError
        from decimal import Decimal

        errs = {}
        if self.start_date and self.end_date and self.end_date < self.start_date:
            errs["end_date"] = "End date cannot be earlier than start date."
        if self.funding_limit is not None and self.funding_limit <= Decimal("0"):
            errs["funding_limit"] = "Funding limit must be a positive amount when set."
        if errs:
            raise ValidationError(errs)

    @property
    def is_closed(self) -> bool:
        return self.status == self.Status.CLOSED

    @property
    def days_until_end(self):
        from django.utils import timezone

        if not self.end_date:
            return None
        return (self.end_date - timezone.now().date()).days


class DonorAgreementGrant(models.Model):
    """Link a donor agreement to one or more post-award grants (grant agreement control)."""

    agreement = models.ForeignKey(
        DonorAgreement, on_delete=models.CASCADE, related_name="grant_links"
    )
    grant = models.ForeignKey(
        "Grant", on_delete=models.PROTECT, related_name="donor_agreement_links"
    )

    class Meta:
        ordering = ["agreement", "grant"]
        constraints = [
            models.UniqueConstraint(fields=["agreement", "grant"], name="uniq_donor_agreement_grant"),
        ]

    def __str__(self) -> str:
        return f"{self.agreement.agreement_code} → {self.grant.code}"


class DonorAgreementProject(models.Model):
    """Link a donor agreement to program/projects."""

    agreement = models.ForeignKey(
        DonorAgreement, on_delete=models.CASCADE, related_name="project_links"
    )
    project = models.ForeignKey(
        "Project", on_delete=models.PROTECT, related_name="donor_agreement_links"
    )

    class Meta:
        ordering = ["agreement", "project"]
        constraints = [
            models.UniqueConstraint(
                fields=["agreement", "project"], name="uniq_donor_agreement_project"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.agreement.agreement_code} → {self.project.code}"


class DonorAgreementAttachment(models.Model):
    """Amendments and supporting documents (signed PDF typically on DonorAgreement.file)."""

    class Kind(models.TextChoices):
        AMENDMENT = "amendment", "Amendment"
        SUPPORTING = "supporting", "Supporting document"
        OTHER = "other", "Other"

    agreement = models.ForeignKey(
        DonorAgreement, on_delete=models.CASCADE, related_name="attachments"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.SUPPORTING)
    file = models.FileField(upload_to="grants/agreement_attachments/%Y/%m/")
    original_filename = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self) -> str:
        return self.original_filename or str(self.pk)


class DonorRestriction(models.Model):
    """
    Donor-specific conditions and restrictions for NGO compliance: budget, procurement,
    eligibility, reporting, audit. Used for validation hooks on journals, budgets, and PRs.
    """

    class Category(models.TextChoices):
        BUDGET = "budget", "Budget restrictions"
        PROCUREMENT = "procurement", "Procurement restrictions"
        GEOGRAPHIC = "geographic", "Geographic restrictions"
        ACTIVITY = "activity", "Activity restrictions"
        COST_ELIGIBILITY = "cost_eligibility", "Cost eligibility rules"
        TIME = "time", "Time restrictions"
        REPORTING = "reporting", "Reporting restrictions"
        HR = "hr", "HR restrictions"
        AUDIT = "audit", "Audit requirements"
        OTHER = "other", "Other"

    class RestrictionType(models.TextChoices):
        # Legacy / general (kept for backward compatibility)
        BUDGET_LINE = "budget_line", "Budget line restriction"
        PROCUREMENT = "procurement", "Procurement rules"
        REPORTING = "reporting", "Reporting requirement"
        OTHER = "other", "Other"
        # Budget
        BUDGET_ALLOWED_LINES = "budget_allowed_lines", "Specific budget lines allowed"
        BUDGET_CATEGORY_CAP = "budget_category_cap", "Spending cap per category"
        # Procurement
        PROC_METHOD_REQUIRED = "proc_method_required", "Procurement method required"
        PROC_MIN_QUOTES = "proc_min_quotes", "Minimum quotation requirements"
        PROC_VENDOR_CONDITIONS = "proc_vendor_conditions", "Preferred vendor conditions"
        # Geographic
        GEO_ALLOWED_LOCATIONS = "geo_allowed_locations", "Allowed project locations"
        GEO_RESTRICTED_REGIONS = "geo_restricted_regions", "Restricted countries/regions"
        # Activity
        ACT_ALLOWED = "act_allowed", "Allowed activities"
        ACT_PROHIBITED = "act_prohibited", "Prohibited activities"
        # Cost eligibility
        COST_ELIGIBLE_LIST = "cost_eligible_list", "Eligible expenses list"
        COST_INELIGIBLE_CATEGORIES = "cost_ineligible_categories", "Ineligible expense categories"
        # Time
        TIME_SPENDING_DEADLINE = "time_spending_deadline", "Spending deadline"
        TIME_UTILIZATION_PERIOD = "time_utilization_period", "Funding utilization period"
        # Reporting
        REP_FINANCIAL_FREQUENCY = "rep_financial_frequency", "Required financial report frequency"
        REP_NARRATIVE = "rep_narrative", "Required narrative reports"
        # HR
        HR_STAFFING_LIMIT = "hr_staffing_limit", "Staffing cost limits"
        HR_SALARY_CAP = "hr_salary_cap", "Salary caps"
        # Audit
        AUDIT_MANDATORY = "audit_mandatory", "Mandatory audit"
        AUDIT_SPECIAL = "audit_special", "Special audit conditions"

    class ComplianceLevel(models.TextChoices):
        MANDATORY = "mandatory", "Mandatory"
        RECOMMENDED = "recommended", "Recommended"
        INFORMATIONAL = "informational", "Informational"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        EXPIRED = "expired", "Expired"

    class AppliesScope(models.TextChoices):
        DONOR_WIDE = "donor_wide", "Entire donor"
        FUNDING_SOURCE = "funding_source", "Specific funding source"
        GRANT = "grant", "Specific grant"
        PROJECT = "project", "Specific project"

    restriction_code = models.CharField(
        max_length=32,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="Unique reference (auto-generated if left blank).",
    )
    donor = models.ForeignKey(Donor, on_delete=models.CASCADE, related_name="restrictions")
    funding_source = models.ForeignKey(
        "FundingSource",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="donor_restrictions",
    )
    grant = models.ForeignKey(
        "Grant",
        on_delete=models.SET_NULL,
        related_name="donor_restriction_records",
        null=True,
        blank=True,
    )
    project = models.ForeignKey(
        "Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="donor_restrictions",
    )
    budget_line = models.ForeignKey(
        "BudgetLine",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="donor_restrictions",
        help_text="Optional link to a specific budget line when restriction applies to one line.",
    )
    account_category = models.ForeignKey(
        "tenant_finance.AccountCategory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="donor_restrictions",
        help_text="Optional expense category for eligibility / cap rules.",
    )
    category = models.CharField(
        max_length=30,
        choices=Category.choices,
        default=Category.OTHER,
        db_index=True,
    )
    restriction_type = models.CharField(
        max_length=40,
        choices=RestrictionType.choices,
        default=RestrictionType.OTHER,
        db_index=True,
    )
    compliance_level = models.CharField(
        max_length=20,
        choices=ComplianceLevel.choices,
        default=ComplianceLevel.MANDATORY,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    effective_start = models.DateField(null=True, blank=True, db_index=True)
    effective_end = models.DateField(null=True, blank=True, db_index=True)
    applies_scope = models.CharField(
        max_length=20,
        choices=AppliesScope.choices,
        default=AppliesScope.DONOR_WIDE,
        help_text="Primary applicability; align with funding source / grant / project when set.",
    )
    description = models.TextField(help_text="Summary shown in lists and alerts.")
    conditions = models.TextField(blank=True, help_text="Detailed enforceable conditions.")
    internal_notes = models.TextField(blank=True, help_text="Internal notes (not shown to donors).")
    enforce_budget_validation = models.BooleanField(default=False)
    enforce_procurement_validation = models.BooleanField(default=False)
    enforce_expense_eligibility = models.BooleanField(default=False)
    require_supporting_documents = models.BooleanField(default=False)
    require_approval_override = models.BooleanField(
        default=False,
        help_text="If set, violations may be waived only with an approved override.",
    )
    max_budget_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum % of budget that may be used under this rule (when applicable).",
    )
    max_expense_per_transaction = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    max_procurement_threshold = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["donor", "status"]),
            models.Index(fields=["grant", "status"]),
            models.Index(fields=["restriction_type"]),
            models.Index(fields=["status", "effective_end"]),
            models.Index(fields=["effective_start", "effective_end"]),
        ]

    def __str__(self) -> str:
        code = self.restriction_code or f"#{self.pk}"
        return f"{code} — {self.donor.name}"

    def save(self, *args, **kwargs):
        if self.restriction_code == "":
            self.restriction_code = None
        super().save(*args, **kwargs)
        if not self.restriction_code:
            code = f"DRC-{self.pk:06d}"
            n = 0
            while (
                DonorRestriction.objects.filter(restriction_code=code)
                .exclude(pk=self.pk)
                .exists()
            ):
                n += 1
                code = f"DRC-{self.pk:06d}-{n}"
            DonorRestriction.objects.filter(pk=self.pk).update(restriction_code=code)
            self.restriction_code = code

    def clean(self) -> None:
        from decimal import Decimal

        errs = {}
        if self.effective_start and self.effective_end and self.effective_end < self.effective_start:
            errs["effective_end"] = _("Effective end cannot be before start.")
        if self.max_budget_percentage is not None and (
            self.max_budget_percentage < Decimal("0") or self.max_budget_percentage > Decimal("100")
        ):
            errs["max_budget_percentage"] = _("Must be between 0 and 100.")
        if self.applies_scope == self.AppliesScope.FUNDING_SOURCE and not self.funding_source_id:
            errs["funding_source"] = _("Select a funding source for this scope.")
        if self.applies_scope == self.AppliesScope.GRANT and not self.grant_id:
            errs["grant"] = _("Select a grant for this scope.")
        if self.applies_scope == self.AppliesScope.PROJECT and not self.project_id:
            errs["project"] = _("Select a project for this scope.")
        if errs:
            raise ValidationError(errs)

    @property
    def description_summary(self) -> str:
        t = (self.description or "").strip()
        return t[:120] + ("…" if len(t) > 120 else "")

    def sync_expired_status(self) -> bool:
        """Set status to EXPIRED if end date passed; returns True if updated."""
        from django.utils import timezone

        today = timezone.now().date()
        if (
            self.status == self.Status.ACTIVE
            and self.effective_end
            and self.effective_end < today
        ):
            DonorRestriction.objects.filter(pk=self.pk).update(status=self.Status.EXPIRED)
            self.status = self.Status.EXPIRED
            return True
        return False


class GrantAllocation(models.Model):
    """Multi-donor: allocate multiple donors to a single grant with amount or percentage."""

    grant = models.ForeignKey("Grant", on_delete=models.CASCADE, related_name="allocations")
    donor = models.ForeignKey(Donor, on_delete=models.PROTECT, related_name="grant_allocations")
    amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["grant", "donor"]
        unique_together = ("grant", "donor")

    def __str__(self) -> str:
        return f"{self.grant.code} — {self.donor.name}"


class ReportingRequirement(models.Model):
    """Donor reporting templates and formats."""

    class Frequency(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Quarterly"
        ANNUAL = "annual", "Annual"
        AD_HOC = "ad_hoc", "Ad hoc"

    donor = models.ForeignKey(
        Donor, on_delete=models.CASCADE, related_name="reporting_requirements"
    )
    name = models.CharField(max_length=120)
    format_description = models.CharField(max_length=255, blank=True)
    frequency = models.CharField(
        max_length=20, choices=Frequency.choices, default=Frequency.QUARTERLY, blank=True
    )
    template_notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["donor", "name"]

    def __str__(self) -> str:
        return f"{self.donor.name}: {self.name}"


class ReportingDeadline(models.Model):
    """Report submission deadlines and status."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUBMITTED = "submitted", "Submitted"
        OVERDUE = "overdue", "Overdue"

    donor = models.ForeignKey(
        Donor, on_delete=models.CASCADE, related_name="reporting_deadlines", null=True, blank=True
    )
    grant = models.ForeignKey(
        "Grant", on_delete=models.CASCADE, related_name="reporting_deadlines", null=True, blank=True
    )
    requirement = models.ForeignKey(
        ReportingRequirement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deadlines",
    )
    title = models.CharField(max_length=200)
    deadline_date = models.DateField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["deadline_date", "id"]

    def __str__(self) -> str:
        return f"{self.title} — {self.deadline_date}"


class Project(models.Model):
    """Project dimension for linking grant tracking, agreements, and financial mapping."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PLANNING = "planning", "Planning"
        ACTIVE = "active", "Active"
        ON_HOLD = "on_hold", "On hold"
        CLOSED = "closed", "Closed"
        COMPLETED = "completed", "Completed"

    class FundingType(models.TextChoices):
        """Aligned with common grant funding categories (optional on project master)."""

        PROJECT = "project", "Project grant"
        CORE = "core", "Core / institutional"
        EMERGENCY = "emergency", "Emergency"
        INSTITUTIONAL = "institutional", "Institutional"
        OTHER = "other", "Other"

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    donor = models.ForeignKey(
        Donor, on_delete=models.PROTECT, null=True, blank=True, related_name="projects"
    )
    project_manager = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="projects_managed",
    )
    location = models.CharField(
        max_length=255,
        blank=True,
        help_text="Primary implementation location (region, site, or country).",
    )
    program_sector = models.CharField(
        max_length=120,
        blank=True,
        help_text="Program, sector, or thematic area.",
    )
    funding_type = models.CharField(
        max_length=30,
        choices=FundingType.choices,
        blank=True,
        help_text="Primary funding modality for this project (optional).",
    )
    currency = models.ForeignKey(
        "tenant_finance.Currency",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="projects",
        help_text="Default reporting currency when multiple grants use different currencies.",
    )
    total_beneficiaries = models.PositiveIntegerField(
        default=0,
        help_text="Planned or reported beneficiaries (summary field).",
    )
    start_date = models.DateField(null=True, blank=True)
    # Legacy end_date kept for backward compatibility (treated as original end date).
    end_date = models.DateField(null=True, blank=True)
    original_end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Original planned project end date (baseline).",
    )
    revised_end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Revised end date after approved extensions (optional).",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PLANNING, db_index=True
    )
    # Keep is_active for backward compatibility; treat ACTIVE status as open for transactions.
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"

    @property
    def title(self) -> str:
        """Alias for list/report columns expecting project title."""
        return self.name

    @property
    def is_open_for_transactions(self) -> bool:
        """Project is open for posting when status is Active."""
        return self.status == self.Status.ACTIVE

    def calendar_phase_label(self, today=None) -> str | None:
        """
        Read-only lifecycle hint from dates (does not replace stored workflow status).
        Returns None if dates are insufficient.
        """
        from datetime import date

        d = today or date.today()
        if self.start_date and d < self.start_date:
            return "Upcoming"
        end = self.effective_end_date()
        if end and d > end:
            return "Ended"
        if self.start_date and end and self.start_date <= d <= end:
            return "In period"
        return None

    def effective_end_date(self):
        return self.revised_end_date or self.original_end_date or self.end_date

    def is_active_on(self, dt) -> bool:
        if not dt:
            return False
        if not self.is_open_for_transactions:
            return False
        if self.start_date and dt < self.start_date:
            return False
        end = self.effective_end_date()
        if end and dt > end:
            return False
        return True

    def clean(self) -> None:
        from django.core.exceptions import ValidationError

        errors = {}
        if not self.code or not self.code.strip():
            errors["code"] = "Project code is required."
        if self.start_date and self.end_date and self.start_date > self.end_date:
            errors["end_date"] = "End date must be on or after start date."
        # Keep baseline fields consistent
        if not self.original_end_date and self.end_date:
            self.original_end_date = self.end_date
        if self.original_end_date and self.start_date and self.start_date > self.original_end_date:
            errors["original_end_date"] = "Original end date must be on or after start date."
        if self.revised_end_date and self.original_end_date and self.revised_end_date < self.original_end_date:
            errors["revised_end_date"] = "Revised end date must be on or after original end date."
        if errors:
            raise ValidationError(errors)


class GrantTracking(models.Model):
    """
    Pre-award pipeline: opportunities before donor contract is signed.
    Does not create accounting transactions. Approved records can be converted to Grant Agreements.
    """

    class PipelineStage(models.TextChoices):
        OPPORTUNITY = "opportunity", "Opportunity"
        CONCEPT_NOTE = "concept_note", "Concept Note"
        PROPOSAL_PREPARATION = "proposal_preparation", "Proposal Preparation"
        PROPOSAL_SUBMITTED = "proposal_submitted", "Proposal Submitted"
        UNDER_REVIEW = "under_review", "Under Review"
        CLARIFICATION_REQUESTED = "clarification_requested", "Clarification Requested"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    class GrantType(models.TextChoices):
        INSTITUTIONAL = "institutional", "Institutional Grant"
        PROJECT = "project", "Project Grant"
        EMERGENCY = "emergency", "Emergency Grant"
        CORE = "core", "Core Funding"
        SUB_GRANT = "sub_grant", "Sub-Grant"
        MULTI_DONOR = "multi_donor", "Multi-Donor Grant"
        OTHER = "other", "Other"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    code = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=255)
    donor = models.ForeignKey(Donor, on_delete=models.PROTECT, related_name="grant_trackings")
    pipeline_stage = models.CharField(
        max_length=30, choices=PipelineStage.choices, default=PipelineStage.OPPORTUNITY, db_index=True
    )
    grant_type = models.CharField(
        max_length=20, choices=GrantType.choices, default=GrantType.OTHER, blank=True
    )
    priority = models.CharField(
        max_length=20, choices=Priority.choices, default=Priority.MEDIUM, blank=True
    )
    grant_manager = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.PROTECT,
        related_name="grant_trackings_managed",
        null=True,
        blank=True,
    )
    submission_deadline = models.DateField(null=True, blank=True)
    date_submitted = models.DateField(null=True, blank=True)
    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="grant_trackings",
    )
    project_name = models.CharField(max_length=255, blank=True)
    amount_requested = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    amount_awarded = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Optional; cannot exceed amount requested unless override.",
    )
    grant_owner = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-created_at"]
        verbose_name = "Grant tracking (pre-award)"
        verbose_name_plural = "Grant trackings (pre-award)"

    def __str__(self) -> str:
        return f"{self.code} — {self.title}"

    def can_convert_to_agreement(self) -> bool:
        if self.pipeline_stage != self.PipelineStage.APPROVED:
            return False
        db = getattr(self._state, "db", None) or "default"
        return not Grant.objects.using(db).filter(source_tracking=self).exists()

    def can_delete(self) -> bool:
        return self.pipeline_stage == self.PipelineStage.OPPORTUNITY


class GrantTrackingDocument(models.Model):
    """ZIP or other documents attached to a grant tracking record."""

    tracking = models.ForeignKey(
        GrantTracking, on_delete=models.CASCADE, related_name="documents"
    )
    file = models.FileField(upload_to="grants/tracking_docs/%Y/%m/")
    original_filename = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self) -> str:
        return self.original_filename or str(self.file)


class Grant(models.Model):
    """
    Post-award signed contract (Grant Agreement). Created from an approved GrantTracking
    or by authorized manual entry. Once active, the official source for incoming funds,
    utilization, and donor reporting.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        CLOSED = "closed", "Closed"

    class GrantType(models.TextChoices):
        FEDERAL = "federal", "Federal Government"
        STATE_LOCAL = "state_local", "State / Local Gov't"
        ASSOCIATION = "association", "Association"
        CORPORATE = "corporate", "Corporate Foundation"
        PRIVATE = "private", "Private Foundation"
        OTHER = "other", "Other"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    code = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=255)
    donor = models.ForeignKey(Donor, on_delete=models.PROTECT, related_name="grants")
    project = models.ForeignKey(
        Project,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="grants",
        help_text="Grant must belong to a project for transaction posting.",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    # Link to pre-award tracking (null = manual agreement entry)
    source_tracking = models.OneToOneField(
        GrantTracking,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="grant_agreement",
        help_text="Approved tracking record this agreement was created from.",
    )
    grant_type = models.CharField(
        max_length=20, choices=GrantType.choices, default=GrantType.OTHER, blank=True
    )
    priority = models.CharField(
        max_length=20, choices=Priority.choices, default=Priority.MEDIUM, blank=True
    )
    submission_deadline = models.DateField(null=True, blank=True)
    date_submitted = models.DateField(null=True, blank=True)
    project_name = models.CharField(max_length=255, blank=True)
    start_date = models.DateField(null=True, blank=True)
    # Legacy end_date kept for backward compatibility (treated as original end date).
    end_date = models.DateField(null=True, blank=True)
    original_end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Original planned grant end date (baseline).",
    )
    revised_end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Revised end date after approved extensions (optional).",
    )
    amount_requested = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    bank_account = models.ForeignKey(
        "tenant_finance.BankAccount",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Primary bank account where donor funds are received for this grant.",
    )
    currency = models.ForeignKey(
        "tenant_finance.Currency",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="grants",
    )
    award_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    signed_date = models.DateField(
        null=True, blank=True, help_text="Date the agreement was signed."
    )
    reporting_rules = models.TextField(
        blank=True, help_text="Donor reporting requirements summary for this agreement."
    )
    donor_restrictions = models.TextField(
        blank=True, help_text="Donor conditions and restrictions for this agreement."
    )
    signed_contract_document = models.FileField(
        upload_to="grants/agreement_contracts/%Y/%m/", null=True, blank=True
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def effective_end_date(self):
        return self.revised_end_date or self.original_end_date or self.end_date

    def is_active_on(self, dt) -> bool:
        if not dt:
            return False
        if self.status != self.Status.ACTIVE:
            return False
        if self.start_date and dt < self.start_date:
            return False
        end = self.effective_end_date()
        if end and dt > end:
            return False
        # Project must also be active on date if linked
        if self.project_id and not self.project.is_active_on(dt):
            return False
        return True

    def clean(self) -> None:
        from django.core.exceptions import ValidationError

        errors = {}
        if not self.original_end_date and self.end_date:
            self.original_end_date = self.end_date
        if self.original_end_date and self.start_date and self.start_date > self.original_end_date:
            errors["original_end_date"] = "Original end date must be on or after start date."
        if self.revised_end_date and self.original_end_date and self.revised_end_date < self.original_end_date:
            errors["revised_end_date"] = "Revised end date must be on or after original end date."
        if not self.code or not self.code.strip():
            errors["code"] = "Grant code is required."
        if self.start_date and self.end_date and self.start_date > self.end_date:
            errors["end_date"] = "End date must be on or after start date."
        # Budget must be greater than zero for active grants
        if self.award_amount is not None and self.award_amount <= 0:
            errors["award_amount"] = "Budget (award amount) must be greater than zero."
        # Grant must belong to a project
        if not self.project_id:
            errors["project"] = "Grant must belong to a project."
        if errors:
            raise ValidationError(errors)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.code} — {self.title}"


class ProjectPeriodExtension(models.Model):
    """Approved project period extensions (history)."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="period_extensions")
    revised_end_date = models.DateField()
    reason = models.CharField(max_length=255, blank=True)
    approved_by = models.ForeignKey(
        "tenant_users.TenantUser", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-revised_end_date", "-id"]

    def clean(self) -> None:
        from django.core.exceptions import ValidationError

        errors = {}
        if self.project_id and self.revised_end_date:
            baseline = self.project.original_end_date or self.project.end_date
            if baseline and self.revised_end_date < baseline:
                errors["revised_end_date"] = "Extension end date must be on or after original end date."
        if errors:
            raise ValidationError(errors)


class GrantPeriodExtension(models.Model):
    """Approved grant period extensions (history)."""

    grant = models.ForeignKey(Grant, on_delete=models.CASCADE, related_name="period_extensions")
    revised_end_date = models.DateField()
    reason = models.CharField(max_length=255, blank=True)
    approved_by = models.ForeignKey(
        "tenant_users.TenantUser", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-revised_end_date", "-id"]

    def clean(self) -> None:
        from django.core.exceptions import ValidationError

        errors = {}
        if self.grant_id and self.revised_end_date:
            baseline = self.grant.original_end_date or self.grant.end_date
            if baseline and self.revised_end_date < baseline:
                errors["revised_end_date"] = "Extension end date must be on or after original end date."
        if errors:
            raise ValidationError(errors)


class ProjectBudget(models.Model):
    """Project-level budget container (e.g. operational envelope). Links to project master."""

    project = models.ForeignKey(
        "Project", on_delete=models.CASCADE, related_name="project_budgets"
    )
    name = models.CharField(max_length=120, default="Main")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["project", "name"]
        constraints = [
            models.UniqueConstraint(fields=["project", "name"], name="uniq_project_budget_project_name"),
        ]

    def __str__(self) -> str:
        return f"{self.project.code}: {self.name}"


class ProjectBudgetLine(models.Model):
    """
    Budget line under a project budget: category, optional GL account, allocated vs remaining (remaining updated from posted expenses).
    """

    project_budget = models.ForeignKey(
        ProjectBudget, on_delete=models.CASCADE, related_name="lines"
    )
    account = models.ForeignKey(
        "tenant_finance.ChartAccount",
        on_delete=models.PROTECT,
        related_name="project_budget_lines",
        null=True,
        blank=True,
    )
    category = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True)
    allocated_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    remaining_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        help_text="Updated from posted expenses tagged to this line; equals allocated minus actual when synced.",
    )
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["project_budget", "id"]

    def __str__(self) -> str:
        return f"{self.project_budget.project.code} — {self.category}"

    def clean(self) -> None:
        from decimal import Decimal

        errs = {}
        if self.allocated_amount is not None and self.allocated_amount < Decimal("0"):
            errs["allocated_amount"] = _("Allocated amount cannot be negative.")
        if errs:
            raise ValidationError(errs)

    @property
    def project(self):
        return self.project_budget.project


class WorkplanActivity(models.Model):
    """
    Grant workplan activity: one row per activity linked to a grant.
    Workplan ID is auto-generated (code); filters: Grant, Donor, Workplan Status,
    Responsible Department, Activity Status, Start/End Date.
    """

    class WorkplanStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"

    class ActivityStatus(models.TextChoices):
        PLANNED = "planned", "Planned"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"

    class PRStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        SUBMITTED = "submitted", "Submitted"
        APPROVED = "approved", "Approved"
        ORDERED = "ordered", "Ordered"
        RECEIVED = "received", "Received"
        CLOSED = "closed", "Closed"
        NONE = "none", "—"

    grant = models.ForeignKey(
        Grant, on_delete=models.CASCADE, related_name="workplan_activities"
    )
    donor = models.ForeignKey(
        Donor, on_delete=models.PROTECT, related_name="workplan_activities", null=True, blank=True
    )
    project = models.ForeignKey(
        "Project",
        on_delete=models.PROTECT,
        related_name="workplan_activities",
        null=True,
        blank=True,
        help_text="Implementation project; synced from grant.project when set.",
    )
    project_budget_line = models.ForeignKey(
        ProjectBudgetLine,
        on_delete=models.PROTECT,
        related_name="workplan_activities",
        null=True,
        blank=True,
        help_text="Required when the project uses a project budget structure.",
    )
    workplan_code = models.CharField(
        max_length=30, unique=True, blank=True, help_text="Auto-generated Workplan ID (e.g. WP-00001)."
    )
    activity_code = models.CharField(
        max_length=40,
        blank=True,
        help_text="Optional short code; defaults to workplan ID when blank.",
    )
    activity = models.CharField(max_length=255)
    description = models.TextField(blank=True, help_text="Extended activity description.")
    component_output = models.CharField(max_length=255, blank=True)
    budget_line = models.CharField(
        max_length=120, blank=True, help_text="Budget line or category for this activity."
    )
    procurement_requirement = models.TextField(
        blank=True, help_text="Description of procurement need for this activity."
    )
    approved_for_pr = models.BooleanField(
        default=False,
        help_text="When True, a Purchase Requisition can be raised from this activity.",
    )
    responsible_department = models.CharField(max_length=120, blank=True)
    responsible_staff = models.CharField(max_length=120, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    budget_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        default=0,
        help_text="Planned cost for this activity (must fit within budget line envelope).",
    )
    actual_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        help_text="Posted expense total tagged to this activity (system-maintained).",
    )
    pr_number = models.CharField(max_length=80, blank=True)
    pr_status = models.CharField(
        max_length=20, choices=PRStatus.choices, default=PRStatus.NONE, blank=True
    )
    activity_status = models.CharField(
        max_length=20,
        choices=ActivityStatus.choices,
        default=ActivityStatus.PLANNED,
    )
    workplan_status = models.CharField(
        max_length=20,
        choices=WorkplanStatus.choices,
        default=WorkplanStatus.ACTIVE,
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Workplan activity"
        verbose_name_plural = "Workplan activities"

    def __str__(self) -> str:
        return f"{self.workplan_code or self.pk} — {self.activity}"

    def donor_display(self):
        return self.donor.name if self.donor else (self.grant.donor.name if self.grant else "")

    def save(self, *args, **kwargs):
        if self.grant_id and getattr(self.grant, "project_id", None):
            self.project_id = self.grant.project_id
        super().save(*args, **kwargs)
        if not self.workplan_code:
            self.workplan_code = f"WP-{self.pk:05d}"
            db = kwargs.get("using") or self._state.db
            WorkplanActivity.objects.using(db).filter(pk=self.pk).update(workplan_code=self.workplan_code)
        if not (self.activity_code or "").strip():
            db = kwargs.get("using") or self._state.db
            WorkplanActivity.objects.using(db).filter(pk=self.pk).update(activity_code=self.workplan_code)
            self.activity_code = self.workplan_code

    def clean(self) -> None:
        from decimal import Decimal
        from django.db.models import Sum

        errs = {}
        exp_proj = None
        if self.grant_id:
            exp_proj = self.grant.project_id
            if self.project_id and exp_proj and self.project_id != exp_proj:
                errs["project"] = _("Activity project must match the grant's project.")
        if self.project_budget_line_id:
            pb_proj = self.project_budget_line.project_budget.project_id
            line_exp_proj = self.project_id or exp_proj
            if line_exp_proj and pb_proj != line_exp_proj:
                errs["project_budget_line"] = _("Budget line must belong to the same project as the grant.")
            planned = self.budget_amount or Decimal("0")

            db = getattr(self._state, "db", None) or "default"
            qs = WorkplanActivity.objects.using(db).filter(project_budget_line_id=self.project_budget_line_id)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            others = qs.aggregate(s=Sum("budget_amount")).get("s") or Decimal("0")
            cap = self.project_budget_line.allocated_amount or Decimal("0")
            if cap and (others + planned) > cap:
                errs["budget_amount"] = _(
                    "Planned cost for this line would exceed the budget line allocation (%(cap)s). "
                    "Other activities on this line: %(others)s."
                ) % {"cap": cap, "others": others}
        if errs:
            raise ValidationError(errs)

    def can_raise_pr(self):
        """True if this activity is valid for raising a PR (approved and within budget)."""
        return bool(self.approved_for_pr and self.grant_id)

    def total_pr_value(self, using="default"):
        """Sum of estimated_total_cost of PRs linked to this activity."""
        from django.db.models import Sum
        total = (
            PurchaseRequisition.objects.using(using)
            .filter(workplan_activity=self)
            .aggregate(s=Sum("estimated_total_cost"))
            .get("s")
        )
        return total or 0

    def remaining_budget_for_pr(self, using="default"):
        """Activity budget minus total PR value (for validation)."""
        from decimal import Decimal
        budget = self.budget_amount or Decimal("0")
        return budget - self.total_pr_value(using=using)


class PurchaseRequisition(models.Model):
    """
    Purchase Requisition raised from an approved workplan activity.
    Workflow: Draft → Pending Line Manager Approval → Approved by Line Manager →
    Assigned to Procurement → Under Procurement Processing → PO Issued → Fulfilled.
    Terminal: Rejected, Cancelled. Segregation: requester submits; line manager approves/rejects/returns;
    procurement officer processes only after line manager approval.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING_LINE_MANAGER_APPROVAL = "pending_line_manager_approval", "Pending Line Manager Approval"
        APPROVED_BY_LINE_MANAGER = "approved_by_line_manager", "Approved by Line Manager"
        ASSIGNED_TO_PROCUREMENT = "assigned_to_procurement", "Assigned to Procurement"
        UNDER_PROCUREMENT_PROCESSING = "under_procurement_processing", "Under Procurement Processing"
        PO_ISSUED = "po_issued", "PO Issued"
        FULFILLED = "fulfilled", "Fulfilled"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    class ProcurementMethod(models.TextChoices):
        OPEN_TENDER = "open_tender", "Open Tender"
        REQUEST_QUOTATION = "request_quotation", "Request for Quotation"
        DIRECT_PURCHASE = "direct_purchase", "Direct Purchase"
        FRAMEWORK = "framework", "Framework Agreement"
        OTHER = "other", "Other"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    pr_number = models.CharField(max_length=50, unique=True)
    pr_date = models.DateField()
    grant = models.ForeignKey(
        Grant, on_delete=models.PROTECT, related_name="purchase_requisitions"
    )
    donor = models.ForeignKey(
        Donor, on_delete=models.PROTECT, related_name="purchase_requisitions", null=True, blank=True
    )
    workplan_activity = models.ForeignKey(
        WorkplanActivity,
        on_delete=models.PROTECT,
        related_name="purchase_requisitions",
        help_text="Approved workplan activity this PR is raised from.",
    )
    budget_line = models.CharField(max_length=120, blank=True)
    item_description = models.TextField()
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    estimated_unit_cost = models.DecimalField(
        max_digits=14, decimal_places=2, default=0
    )
    estimated_total_cost = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text="Quantity × unit cost; validated against activity budget.",
    )
    procurement_method = models.CharField(
        max_length=30,
        choices=ProcurementMethod.choices,
        default=ProcurementMethod.OTHER,
        blank=True,
    )
    priority = models.CharField(
        max_length=20, choices=Priority.choices, default=Priority.MEDIUM
    )
    delivery_date = models.DateField(
        null=True, blank=True,
        help_text="Requested or expected delivery date.",
    )
    justification = models.TextField(blank=True)
    status = models.CharField(
        max_length=45, choices=Status.choices, default=Status.DRAFT
    )
    notes = models.TextField(blank=True)
    # Requester and workflow audit
    requested_by = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.PROTECT,
        related_name="purchase_requisitions_requested",
        null=True,
        blank=True,
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    line_manager_approved_at = models.DateTimeField(null=True, blank=True)
    line_manager_approved_by = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.PROTECT,
        related_name="pr_approved_by_line_manager",
        null=True,
        blank=True,
    )
    line_manager_rejection_comment = models.TextField(blank=True)
    line_manager_return_comment = models.TextField(blank=True)
    assigned_to_procurement_at = models.DateTimeField(null=True, blank=True)
    procurement_officer = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.PROTECT,
        related_name="pr_assigned_to_procurement",
        null=True,
        blank=True,
    )
    po_issued_at = models.DateTimeField(null=True, blank=True)
    fulfilled_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.PROTECT,
        related_name="pr_cancelled",
        null=True,
        blank=True,
    )
    cancellation_comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-pr_date", "-created_at"]
        verbose_name = "Purchase requisition"
        verbose_name_plural = "Purchase requisitions"

    def __str__(self) -> str:
        return f"{self.pr_number} — {self.workplan_activity.activity if self.workplan_activity_id else ''}"

    def save(self, *args, **kwargs):
        if self.quantity is not None and self.estimated_unit_cost is not None:
            from decimal import Decimal
            self.estimated_total_cost = (self.quantity or Decimal("0")) * (
                self.estimated_unit_cost or Decimal("0")
            )
        super().save(*args, **kwargs)

    def is_terminal(self):
        return self.status in (self.Status.REJECTED, self.Status.CANCELLED, self.Status.FULFILLED)

    def can_line_manager_act(self):
        return self.status == self.Status.PENDING_LINE_MANAGER_APPROVAL

    def can_procurement_act(self):
        return self.status in (
            self.Status.APPROVED_BY_LINE_MANAGER,
            self.Status.ASSIGNED_TO_PROCUREMENT,
            self.Status.UNDER_PROCUREMENT_PROCESSING,
            self.Status.PO_ISSUED,
        )

    def effective_total(self):
        """Total cost from lines if any, else header estimated_total_cost (legacy single-line)."""
        from decimal import Decimal
        lines_total = sum(
            (line.estimated_total_cost or Decimal("0")) for line in self.lines.all()
        )
        if self.lines.exists():
            return lines_total
        return self.estimated_total_cost or Decimal("0")

    def can_edit_lines(self):
        """Only Draft or Returned (Draft) PRs can have lines added/removed."""
        return self.status == self.Status.DRAFT


class PurchaseRequisitionLine(models.Model):
    """Single line item on a Purchase Requisition (activity breakdown)."""

    pr = models.ForeignKey(
        PurchaseRequisition,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    line_number = models.PositiveSmallIntegerField(default=1)
    item_description = models.TextField()
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    estimated_unit_cost = models.DecimalField(
        max_digits=14, decimal_places=2, default=0
    )
    estimated_total_cost = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text="Quantity × unit cost (set in save).",
    )
    budget_line = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["pr", "line_number", "id"]
        verbose_name = "PR line"
        verbose_name_plural = "PR lines"

    def __str__(self) -> str:
        return f"{self.pr.pr_number} line {self.line_number}: {self.item_description[:50]}"

    def save(self, *args, **kwargs):
        from decimal import Decimal
        if self.quantity is not None and self.estimated_unit_cost is not None:
            self.estimated_total_cost = (self.quantity or Decimal("0")) * (
                self.estimated_unit_cost or Decimal("0")
            )
        super().save(*args, **kwargs)


class PurchaseRequisitionStatusLog(models.Model):
    """Audit trail for PR status changes: who, when, from/to status, comment."""

    pr = models.ForeignKey(
        PurchaseRequisition,
        on_delete=models.CASCADE,
        related_name="status_logs",
    )
    from_status = models.CharField(max_length=45, blank=True)
    to_status = models.CharField(max_length=45)
    performed_by = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.PROTECT,
        related_name="pr_status_logs",
        null=True,
        blank=True,
    )
    performed_at = models.DateTimeField(auto_now_add=True)
    comment = models.TextField(blank=True)

    class Meta:
        ordering = ["-performed_at"]
        verbose_name = "PR status log"
        verbose_name_plural = "PR status logs"

    def __str__(self) -> str:
        return f"{self.pr.pr_number} {self.from_status} → {self.to_status}"


class PurchaseRequisitionAttachment(models.Model):
    """File attachment on a Purchase Requisition."""

    pr = models.ForeignKey(
        PurchaseRequisition,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(upload_to="grants/pr_attachments/%Y/%m/")
    original_filename = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.PROTECT,
        related_name="pr_attachments_uploaded",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = "PR attachment"
        verbose_name_plural = "PR attachments"

    def __str__(self) -> str:
        return self.original_filename or str(self.file)


class Supplier(models.Model):
    """Supplier/vendor for procurement."""

    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=60, blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class ProcurementThreshold(models.Model):
    """Procurement method and approval rules by value threshold."""

    class Method(models.TextChoices):
        DIRECT_PURCHASE = "direct_purchase", "Direct Purchase"
        REQUEST_QUOTATION = "request_quotation", "RFQ"
        OPEN_TENDER = "open_tender", "Tender"

    amount_min = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    amount_max = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Null = no upper limit.",
    )
    method = models.CharField(max_length=30, choices=Method.choices)
    requires_po_approval = models.BooleanField(default=False)
    po_approval_limit = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="POs above this need approval.",
    )

    class Meta:
        ordering = ["amount_min"]

    def __str__(self) -> str:
        return f"{self.amount_min}–{self.amount_max or '∞'} → {self.get_method_display()}"

    @classmethod
    def for_amount(cls, amount, using="default"):
        """Return the threshold row where amount_min <= amount < amount_max (or amount_max is null)."""
        from decimal import Decimal
        amt = amount if isinstance(amount, Decimal) else Decimal(str(amount))
        qs = cls.objects.using(using).filter(amount_min__lte=amt).filter(
            models.Q(amount_max__isnull=True) | models.Q(amount_max__gt=amt)
        ).order_by("-amount_min")
        return qs.first()


class PurchaseOrder(models.Model):
    """Purchase Order created from an approved PR. Tracks supplier, lines, and receipt/invoice status."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING_APPROVAL = "pending_approval", "Pending Approval"
        APPROVED = "approved", "Approved"
        SENT = "sent", "Sent to Supplier"
        PARTIALLY_RECEIVED = "partially_received", "Partially Received"
        RECEIVED = "received", "Received"
        CLOSED = "closed", "Closed"
        CANCELLED = "cancelled", "Cancelled"

    pr = models.ForeignKey(
        PurchaseRequisition,
        on_delete=models.PROTECT,
        related_name="purchase_orders",
    )
    po_number = models.CharField(max_length=50, unique=True)
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="purchase_orders",
    )
    procurement_method = models.CharField(
        max_length=30,
        choices=PurchaseRequisition.ProcurementMethod.choices,
        default=PurchaseRequisition.ProcurementMethod.OTHER,
    )
    order_date = models.DateField()
    expected_delivery_date = models.DateField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.DRAFT)
    approved_by = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.PROTECT,
        related_name="po_approved",
        null=True,
        blank=True,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-order_date", "-created_at"]

    def __str__(self) -> str:
        return f"{self.po_number} — {self.supplier.name}"


class PurchaseOrderLine(models.Model):
    """Line on a Purchase Order, linked to PR line."""

    po = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    pr_line = models.ForeignKey(
        PurchaseRequisitionLine,
        on_delete=models.PROTECT,
        related_name="po_lines",
        null=True,
        blank=True,
    )
    item_description = models.TextField()
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    received_quantity = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ["po", "id"]

    def save(self, *args, **kwargs):
        from decimal import Decimal
        if self.quantity is not None and self.unit_price is not None:
            self.amount = (self.quantity or Decimal("0")) * (self.unit_price or Decimal("0"))
        super().save(*args, **kwargs)


class GoodsReceipt(models.Model):
    """Goods receipt against a Purchase Order."""

    po = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.PROTECT,
        related_name="goods_receipts",
    )
    gr_number = models.CharField(max_length=50)
    receipt_date = models.DateField()
    received_by = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.PROTECT,
        related_name="gr_received",
        null=True,
        blank=True,
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-receipt_date", "-created_at"]
        unique_together = [["po", "gr_number"]]

    def __str__(self) -> str:
        return f"{self.gr_number} ({self.po.po_number})"


class GoodsReceiptLine(models.Model):
    """Quantity received per PO line on a Goods Receipt."""

    gr = models.ForeignKey(
        GoodsReceipt,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    po_line = models.ForeignKey(
        PurchaseOrderLine,
        on_delete=models.PROTECT,
        related_name="gr_lines",
    )
    quantity_received = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ["gr", "po_line"]
        unique_together = [["gr", "po_line"]]


class SupplierInvoice(models.Model):
    """Supplier invoice linked to a PO; tracked until payment."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING_APPROVAL = "pending_approval", "Pending Approval"
        APPROVED = "approved", "Approved"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    po = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.PROTECT,
        related_name="invoices",
    )
    invoice_number = models.CharField(max_length=80)
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="invoices",
    )
    invoice_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.DRAFT)
    approved_by = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.PROTECT,
        related_name="invoice_approved",
        null=True,
        blank=True,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    payment_reference = models.CharField(max_length=120, blank=True)
    payment_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-invoice_date", "-created_at"]

    def __str__(self) -> str:
        return f"{self.invoice_number} — {self.po.po_number}"


class GrantDocument(models.Model):
    """Documents attached to a grant (e.g. ZIP uploads for Grant Tracking)."""

    grant = models.ForeignKey(Grant, on_delete=models.CASCADE, related_name="documents")
    file = models.FileField(upload_to="grants/documents/%Y/%m/")
    original_filename = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self) -> str:
        return self.original_filename or str(self.file)


class BudgetLine(models.Model):
    grant = models.ForeignKey(Grant, on_delete=models.CASCADE, related_name="budget_lines")
    # Link to chart of accounts for proper coding of the budget line.
    account = models.ForeignKey(
        "tenant_finance.ChartAccount",
        on_delete=models.PROTECT,
        related_name="budget_lines",
        null=True,
        blank=True,
    )
    category = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["id"]

    def clean(self) -> None:
        from decimal import Decimal

        errors = {}
        if self.amount is not None and self.amount < Decimal("0"):
            errors["amount"] = _("Budget line amount cannot be negative.")
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.grant.code}: {self.category}"


class GrantApproval(models.Model):
    """
    Lightweight approval workflow for grants (tenant DB).
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    grant = models.ForeignKey(Grant, on_delete=models.CASCADE, related_name="approvals")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    requested_by = models.ForeignKey("tenant_users.TenantUser", on_delete=models.PROTECT, related_name="grant_approval_requests")
    decided_by = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="grant_approval_decisions",
    )
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.grant.code} {self.status}"


class GrantAssignment(models.Model):
    """
    Assign a finance officer to a grant (project) for posting responsibilities.

    - Finance officer can only see/post for grants where there is an active assignment.
    - Finance manager can manage all grants and is not restricted by these rows.
    """

    grant = models.ForeignKey(Grant, on_delete=models.CASCADE, related_name="finance_assignments")
    officer = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.CASCADE,
        related_name="grant_assignments",
    )
    is_active = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-assigned_at"]
        unique_together = ("grant", "officer", "is_active")

    def __str__(self) -> str:
        return f"{self.grant.code} → {self.officer.email if hasattr(self.officer, 'email') else self.officer_id}"


class BudgetTemplate(models.Model):
    """
    Reusable budget templates for projects or donors.
    """

    class Scope(models.TextChoices):
        GENERIC = "generic", "Generic"
        PROJECT = "project", "Project / grant"
        DONOR = "donor", "Donor"

    name = models.CharField(max_length=200)
    scope = models.CharField(max_length=20, choices=Scope.choices, default=Scope.GENERIC)
    donor = models.ForeignKey(Donor, on_delete=models.SET_NULL, null=True, blank=True, related_name="budget_templates")
    grant = models.ForeignKey(Grant, on_delete=models.SET_NULL, null=True, blank=True, related_name="budget_templates")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class BudgetTemplateLine(models.Model):
    """
    Lines within a budget template: standard categories and default amounts.
    """

    template = models.ForeignKey(BudgetTemplate, on_delete=models.CASCADE, related_name="lines")
    category = models.CharField(max_length=200)
    default_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    order = models.PositiveIntegerField(default=0)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["template", "order", "id"]

    def __str__(self) -> str:
        return f"{self.template.name}: {self.category}"
