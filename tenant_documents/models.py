from __future__ import annotations

import mimetypes
import os

from django.db import models
from django.utils.translation import gettext_lazy as _


class StorageProvider(models.TextChoices):
    LOCAL = "local", _("Local server (Django media)")
    AWS_S3 = "aws_s3", _("Amazon S3")
    AZURE_BLOB = "azure_blob", _("Azure Blob Storage")
    SHAREPOINT = "sharepoint", _("Microsoft SharePoint")
    GOOGLE_DRIVE = "google_drive", _("Google Drive")
    DROPBOX = "dropbox", _("Dropbox")


class DocumentStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    PENDING_ATTACHMENT = "pending_attachment", _("Pending attachment")
    PENDING_APPROVAL = "pending_approval", _("Pending approval")
    READY_TO_POST = "ready_to_post", _("Ready to post")
    APPROVED = "approved", _("Approved")
    POSTED = "posted", _("Posted / official record")
    REVERSED = "reversed", _("Reversed")
    ARCHIVED = "archived", _("Archived")


class DocumentType(models.TextChoices):
    INVOICE = "invoice", _("Invoice")
    RECEIPT = "receipt", _("Receipt")
    CONTRACT = "contract", _("Contract")
    APPROVAL_MEMO = "approval_memo", _("Approval memo")
    BANK_PROOF = "bank_proof", _("Bank proof")
    DELIVERY_NOTE = "delivery_note", _("Delivery note")
    REQUEST_LETTER = "request_letter", _("Request letter")
    TIMESHEET = "timesheet", _("Timesheet")
    ID_DOCUMENT = "id_document", _("ID document")
    CV = "cv", _("CV / resume")
    DONOR_AGREEMENT = "donor_agreement", _("Donor agreement")
    POLICY = "policy", _("Policy")
    TEMPLATE = "template", _("Template")
    AUDIT_EVIDENCE = "audit_evidence", _("Audit evidence")
    OTHER = "other", _("Other")


DEFAULT_ALLOWED_EXTENSIONS = [
    "pdf",
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp",
    "tif",
    "tiff",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "csv",
    "txt",
    "zip",
    "eml",
    "msg",
]


def _default_allowed_extensions_json():
    return list(DEFAULT_ALLOWED_EXTENSIONS)


def _empty_json_list():
    return []


class DocumentPolicyConfig(models.Model):
    """
    Per-tenant Document Management rules (single row per tenant database).
    Enforces NGO / audit-ready defaults; adjust per organization.
    """

    max_file_size_bytes = models.PositiveIntegerField(
        default=26_214_400,  # 25 MiB
        help_text=_("Maximum upload size in bytes."),
    )
    allowed_extensions = models.JSONField(
        default=_default_allowed_extensions_json,
        help_text=_("Lowercase extensions without dot, e.g. pdf, jpg."),
    )
    allowed_mime_types = models.JSONField(
        null=True,
        blank=True,
        default=_empty_json_list,
        help_text=_("Optional allowlist; empty means infer from extension only."),
    )
    require_category_for_library_upload = models.BooleanField(
        default=True,
        help_text=_("Standalone uploads must select a document category."),
    )
    block_duplicate_files = models.BooleanField(
        default=True,
        help_text=_("Reject uploads when SHA-256 matches an existing document in this tenant."),
    )
    enforce_workflow_transitions = models.BooleanField(
        default=True,
        help_text=_("Restrict status changes to allowed workflow edges."),
    )
    naming_convention_regex = models.CharField(
        max_length=500,
        blank=True,
        help_text=_("Optional full-match regex for original filename (empty = disabled)."),
    )
    default_retention_years = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text=_("Years from upload to retention_until (audit retention); blank = not auto-set."),
    )
    search_query_max_length = models.PositiveSmallIntegerField(default=200)
    search_page_size_default = models.PositiveSmallIntegerField(default=40)
    search_page_size_max = models.PositiveSmallIntegerField(default=100)
    ngo_require_grant_when_entry_has_grant = models.BooleanField(
        default=True,
        help_text=_("Finance-linked documents must carry grant when journal entry has a grant."),
    )
    ngo_warn_missing_journal_document_category = models.BooleanField(
        default=True,
        help_text=_("Log audit warning when journal attachment has no NGO document category."),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Document policy configuration")
        verbose_name_plural = _("Document policy configurations")

    def __str__(self) -> str:
        return "Document policy"

    @classmethod
    def get_solo(cls, using: str | None = None):
        alias = using or "default"
        defaults = {
            "allowed_extensions": DEFAULT_ALLOWED_EXTENSIONS.copy(),
        }
        obj, _ = cls.objects.using(alias).get_or_create(pk=1, defaults=defaults)
        return obj


class StorageProviderConfig(models.Model):
    """
    Per-tenant storage configuration (single logical row per tenant database).
    """

    provider = models.CharField(
        max_length=32,
        choices=StorageProvider.choices,
        default=StorageProvider.LOCAL,
        db_index=True,
    )
    is_active = models.BooleanField(default=True)
    # Future: bucket/container/site id, encrypted connection JSON, etc.
    config_notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Storage provider configuration")
        verbose_name_plural = _("Storage provider configurations")

    def __str__(self) -> str:
        return f"{self.get_provider_display()} ({'active' if self.is_active else 'inactive'})"

    @classmethod
    def get_solo(cls, using: str | None = None):
        alias = using or "default"
        obj, _ = cls.objects.using(alias).get_or_create(pk=1, defaults={"provider": StorageProvider.LOCAL})
        return obj


class DocumentCategory(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, db_index=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    code = models.CharField(max_length=40, blank=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = _("Document category")
        verbose_name_plural = _("Document categories")

    def __str__(self) -> str:
        return self.name


class Document(models.Model):
    """
    Central document record. Files uploaded on transactions are mirrored here
    via sync (see tenant_documents.services.sync) — single physical file.
    """

    file = models.FileField(upload_to="documents/%Y/%m/")
    original_filename = models.CharField(max_length=255, blank=True)
    mime_type = models.CharField(max_length=120, blank=True)
    size_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    file_sha256 = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text=_("SHA-256 hash for duplicate detection and audit integrity."),
    )
    retention_until = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Records retention deadline for NGO / statutory retention."),
    )
    metadata_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("When transaction metadata was last synchronized into this record."),
    )

    category = models.ForeignKey(
        DocumentCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
    )
    document_type = models.CharField(
        max_length=40,
        choices=DocumentType.choices,
        default=DocumentType.OTHER,
        db_index=True,
    )
    tags = models.CharField(
        max_length=500,
        blank=True,
        help_text=_("Comma-separated tags for search and filtering."),
    )

    tenant_key = models.CharField(
        max_length=120,
        blank=True,
        db_index=True,
        help_text=_("Tenant database alias for audit exports."),
    )
    module = models.CharField(max_length=50, blank=True, db_index=True)
    submodule = models.CharField(max_length=50, blank=True, db_index=True)
    linked_record_type = models.CharField(max_length=80, blank=True, db_index=True)
    linked_record_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    voucher_number = models.CharField(max_length=120, blank=True, db_index=True)

    project = models.ForeignKey(
        "tenant_grants.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dm_documents",
    )
    grant = models.ForeignKey(
        "tenant_grants.Grant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dm_documents",
    )
    donor = models.ForeignKey(
        "tenant_grants.Donor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dm_documents",
    )
    employee_record_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    vendor_record_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)

    status = models.CharField(
        max_length=32,
        choices=DocumentStatus.choices,
        default=DocumentStatus.DRAFT,
        db_index=True,
    )
    is_locked = models.BooleanField(
        default=False,
        db_index=True,
        help_text=_("Locked after posting; changes require versioning or reversal."),
    )
    storage_provider = models.CharField(max_length=80, blank=True)
    current_version = models.PositiveIntegerField(default=1)

    uploaded_by = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dm_documents_uploaded",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # Finance journal attachment (single upload — canonical source row)
    source_journal_attachment = models.OneToOneField(
        "tenant_finance.JournalEntryAttachment",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="dm_document",
    )

    class Meta:
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["module", "status"]),
            models.Index(fields=["linked_record_type", "linked_record_id"]),
            models.Index(fields=["uploaded_at"]),
        ]

    def __str__(self) -> str:
        return self.original_filename or self.file.name or f"Document #{self.pk}"

    def refresh_file_metadata(self) -> None:
        name = self.original_filename or (os.path.basename(self.file.name) if self.file else "") or ""
        if name and not self.mime_type:
            mt, _ = mimetypes.guess_type(name)
            self.mime_type = mt or ""
        if self.file and hasattr(self.file, "size") and self.file.size is not None:
            try:
                self.size_bytes = int(self.file.size)
            except (TypeError, ValueError):
                pass


class DocumentVersion(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    file = models.FileField(upload_to="documents/versions/%Y/%m/")
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dm_document_versions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version", "-created_at"]
        unique_together = [("document", "version")]

    def __str__(self) -> str:
        return f"{self.document_id} v{self.version}"


class DocumentLink(models.Model):
    """Additional links from one document to another business object (optional)."""

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="extra_links")
    linked_app_label = models.CharField(max_length=100, db_index=True)
    linked_model_name = models.CharField(
        max_length=100,
        db_index=True,
        help_text=_("Lowercase model name (e.g. grant, purchaserequisition)."),
    )
    object_id = models.PositiveBigIntegerField()
    role = models.CharField(max_length=40, blank=True, help_text=_("e.g. primary, supporting, audit"))

    class Meta:
        indexes = [
            models.Index(
                fields=["linked_app_label", "linked_model_name", "object_id"],
                name="tenant_docu_link_idx",
            ),
        ]


class DocumentApproval(models.Model):
    class State(models.TextChoices):
        PENDING = "pending", _("Pending")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="approvals")
    step = models.PositiveSmallIntegerField(default=1)
    state = models.CharField(max_length=20, choices=State.choices, default=State.PENDING, db_index=True)
    assigned_to = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dm_approvals_assigned",
    )
    decided_by = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dm_approvals_decided",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    comment = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["document_id", "step", "id"]


class DocumentAuditEvent(models.Model):
    """Immutable audit trail rows for uploads, status changes, and version events."""

    class Action(models.TextChoices):
        CREATED = "created", _("Created")
        UPDATED = "updated", _("Metadata updated")
        STATUS = "status", _("Status changed")
        VERSION = "version", _("New version")
        LOCKED = "locked", _("Locked")
        METADATA_SYNC = "metadata_sync", _("Metadata synchronized from transaction")
        COMPLIANCE = "compliance", _("Compliance / validation")

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="audit_events")
    action = models.CharField(max_length=20, choices=Action.choices, db_index=True)
    message = models.CharField(max_length=500, blank=True)
    payload = models.JSONField(null=True, blank=True)
    actor = models.ForeignKey(
        "tenant_users.TenantUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dm_audit_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
