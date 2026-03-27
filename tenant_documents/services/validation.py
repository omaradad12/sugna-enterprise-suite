"""
Central validation for Document Management (per-tenant policy, NGO / audit alignment).

Use from portal views, sync, and future finance attachment uploads so rules stay consistent.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Any

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from tenant_documents.models import (
    DEFAULT_ALLOWED_EXTENSIONS,
    Document,
    DocumentAuditEvent,
    DocumentPolicyConfig,
    DocumentStatus,
    StorageProvider,
    StorageProviderConfig,
)

# --- Status workflow (strict edges for audit) ---
_ALLOWED_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    DocumentStatus.DRAFT: frozenset(
        {
            DocumentStatus.PENDING_ATTACHMENT,
            DocumentStatus.PENDING_APPROVAL,
            DocumentStatus.READY_TO_POST,
            DocumentStatus.APPROVED,
            DocumentStatus.ARCHIVED,
        }
    ),
    DocumentStatus.PENDING_ATTACHMENT: frozenset(
        {
            DocumentStatus.DRAFT,
            DocumentStatus.PENDING_APPROVAL,
            DocumentStatus.READY_TO_POST,
            DocumentStatus.ARCHIVED,
        }
    ),
    DocumentStatus.PENDING_APPROVAL: frozenset(
        {
            DocumentStatus.DRAFT,
            DocumentStatus.READY_TO_POST,
            DocumentStatus.APPROVED,
            DocumentStatus.POSTED,
            DocumentStatus.ARCHIVED,
        }
    ),
    DocumentStatus.READY_TO_POST: frozenset(
        {
            DocumentStatus.PENDING_APPROVAL,
            DocumentStatus.APPROVED,
            DocumentStatus.POSTED,
            DocumentStatus.ARCHIVED,
        }
    ),
    DocumentStatus.APPROVED: frozenset(
        {
            DocumentStatus.POSTED,
            DocumentStatus.PENDING_APPROVAL,
            DocumentStatus.ARCHIVED,
        }
    ),
    DocumentStatus.POSTED: frozenset({DocumentStatus.REVERSED, DocumentStatus.ARCHIVED}),
    DocumentStatus.REVERSED: frozenset({DocumentStatus.ARCHIVED}),
    DocumentStatus.ARCHIVED: frozenset(),
}


def get_policy(using: str) -> DocumentPolicyConfig:
    return DocumentPolicyConfig.get_solo(using=using)


def file_extension(filename: str) -> str:
    base = (filename or "").rsplit(".", 1)
    return base[-1].lower().strip() if len(base) == 2 else ""


def compute_sha256_django_file(f) -> str:
    """Hash a Django FileField / UploadedFile / storage file."""
    h = hashlib.sha256()
    if hasattr(f, "chunks"):
        for chunk in f.chunks():
            h.update(chunk)
    else:
        f.open("rb")
        try:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        finally:
            f.close()
    return h.hexdigest()


def validate_file_size(upload: UploadedFile, policy: DocumentPolicyConfig) -> None:
    size = getattr(upload, "size", None)
    if size is None:
        return
    if size > policy.max_file_size_bytes:
        raise ValidationError(
            _("File exceeds maximum size (%(max)s bytes)."),
            params={"max": policy.max_file_size_bytes},
        )


def validate_extension_and_mime(
    *,
    original_filename: str,
    mime_type: str,
    policy: DocumentPolicyConfig,
) -> None:
    ext = file_extension(original_filename)
    allowed = {e.lower().strip() for e in (policy.allowed_extensions or [])}
    if not allowed:
        allowed = set(DEFAULT_ALLOWED_EXTENSIONS)
    if ext not in allowed:
        raise ValidationError(_("File type not allowed (extension .%(ext)s)."), params={"ext": ext or _("none")})

    mime_allow = [m.strip().lower() for m in (policy.allowed_mime_types or []) if m and str(m).strip()]
    if mime_allow and mime_type:
        m = mime_type.lower().split(";")[0].strip()
        if m not in mime_allow:
            raise ValidationError(_("MIME type not allowed for this organization."))


def validate_naming_convention(original_filename: str, policy: DocumentPolicyConfig) -> None:
    pat = (policy.naming_convention_regex or "").strip()
    if not pat:
        return
    try:
        if not re.fullmatch(pat, original_filename or ""):
            raise ValidationError(_("Filename does not match the required naming convention."))
    except re.error as e:
        raise ValidationError(_("Invalid naming convention regex in policy.")) from e


def validate_upload_for_policy(
    upload: UploadedFile,
    policy: DocumentPolicyConfig,
    *,
    original_name: str | None = None,
) -> None:
    validate_file_size(upload, policy)
    name = original_name or getattr(upload, "name", "") or ""
    mime = getattr(upload, "content_type", "") or ""
    validate_extension_and_mime(original_filename=name, mime_type=mime, policy=policy)
    validate_naming_convention(name, policy)


def find_duplicate_by_hash(using: str, sha256: str, exclude_pk: int | None = None) -> Document | None:
    if not sha256:
        return None
    qs = Document.objects.using(using).filter(file_sha256=sha256)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs.first()


def assert_no_duplicate_upload(
    using: str,
    sha256: str,
    policy: DocumentPolicyConfig,
    exclude_pk: int | None = None,
    *,
    linked_record_type: str = "",
) -> None:
    """
    Block duplicate file content for library / standalone uploads.
    Journal-linked rows may reuse the same scan across vouchers — not blocked here.
    """
    if not policy.block_duplicate_files or not sha256:
        return
    lt = (linked_record_type or "").strip() or "standalone"
    if lt != "standalone":
        return
    if find_duplicate_by_hash(using, sha256, exclude_pk=exclude_pk):
        raise ValidationError(
            _("This file already exists in Document Management (duplicate content)."),
        )


def apply_retention_until(doc: Document, policy: DocumentPolicyConfig) -> None:
    years = policy.default_retention_years
    if not years:
        return
    base = timezone.localdate(doc.uploaded_at) if doc.uploaded_at else timezone.localdate()
    try:
        doc.retention_until = date(base.year + int(years), base.month, base.day)
    except ValueError:
        # Feb 29 → Feb 28
        doc.retention_until = date(base.year + int(years), base.month, 28)


def enrich_document_file_hash_and_retention(doc: Document, using: str, policy: DocumentPolicyConfig) -> None:
    """Compute SHA-256 from stored file, set retention. Call before save."""
    if doc.file:
        doc.refresh_file_metadata()
        doc.file_sha256 = compute_sha256_django_file(doc.file)
    apply_retention_until(doc, policy)


def validate_standalone_library_upload(
    *,
    doc: Document,
    policy: DocumentPolicyConfig,
    using: str,
) -> None:
    """Validate a standalone library document (not journal-synced)."""
    if policy.require_category_for_library_upload and not doc.category_id:
        raise ValidationError(_("Select a document category (required by policy)."))
    assert_no_duplicate_upload(
        using,
        doc.file_sha256,
        policy,
        exclude_pk=doc.pk,
        linked_record_type=doc.linked_record_type or "standalone",
    )
    validate_naming_convention(doc.original_filename or "", policy)


def validate_status_change(
    old_status: str,
    new_status: str,
    policy: DocumentPolicyConfig,
) -> None:
    if old_status == new_status:
        return
    if not policy.enforce_workflow_transitions:
        return
    allowed = _ALLOWED_STATUS_TRANSITIONS.get(old_status)
    if allowed is None or new_status not in allowed:
        raise ValidationError(
            _("Invalid status transition %(from)s → %(to)s."),
            params={"from": old_status, "to": new_status},
        )


def assert_not_locked_for_metadata_change(doc: Document) -> None:
    """Posted / locked records: no in-place file or metadata edits (use versioning)."""
    if doc.is_locked:
        raise ValidationError(_("This document is locked. Create a new version or reverse the journal entry."))


def validate_document_mutation_permission(doc: Document, *, can_manage: bool) -> None:
    """RBAC: locked documents require manage permission for exceptional changes."""
    if doc.is_locked and not can_manage:
        raise ValidationError(_("You do not have permission to change a locked document."))


def validate_finance_link_completeness(
    doc: Document,
    policy: DocumentPolicyConfig,
    *,
    entry: Any,
) -> list[str]:
    """
    NGO-style checks for transaction-linked documents. Returns human-readable warnings (not blocking).
    """
    warnings: list[str] = []
    if not entry or doc.module != "finance":
        return warnings
    if doc.linked_record_type == "journal_entry" and not doc.voucher_number:
        warnings.append("missing_voucher_reference")
    if policy.ngo_require_grant_when_entry_has_grant:
        if getattr(entry, "grant_id", None) and not doc.grant_id:
            warnings.append("grant_not_propagated")
    return warnings


def validate_journal_attachment_category_for_audit(
    attachment: Any,
    policy: DocumentPolicyConfig,
) -> None:
    """Non-blocking policy hook: used only to emit audit events."""
    if policy.ngo_warn_missing_journal_document_category and not (attachment.document_category or "").strip():
        pass
    # Actual audit log is written in sync after document is saved.


def validate_search_params(
    raw_get: dict[str, Any],
    policy: DocumentPolicyConfig,
) -> dict[str, Any]:
    """
    Sanitize list/search/filter query params (length, pagination caps, safe characters).
    """
    max_q = max(1, int(policy.search_query_max_length))
    q = (raw_get.get("q") or "").strip()
    if "\x00" in q:
        q = q.replace("\x00", "")
    q = q[:max_q]

    mod = (raw_get.get("module") or "").strip()[:80]
    st = (raw_get.get("status") or "").strip()[:40]
    dtype = (raw_get.get("document_type") or "").strip()[:40]

    cat_raw = raw_get.get("category")
    category = None
    if cat_raw not in (None, ""):
        try:
            category = int(cat_raw)
        except (TypeError, ValueError):
            category = None

    try:
        page = max(1, int(raw_get.get("page") or 1))
    except (TypeError, ValueError):
        page = 1

    try:
        per_page = int(raw_get.get("per_page") or policy.search_page_size_default)
    except (TypeError, ValueError):
        per_page = policy.search_page_size_default
    cap = max(1, int(policy.search_page_size_max))
    per_page = max(1, min(per_page, cap))

    return {
        "q": q,
        "module": mod,
        "status": st,
        "document_type": dtype,
        "category": category,
        "page": page,
        "per_page": per_page,
    }


def validate_storage_provider_config(
    cfg: StorageProviderConfig,
    policy: DocumentPolicyConfig,
) -> None:
    """Ensure storage provider is a known enum; remote providers require future config."""
    allowed = {c for c, _ in StorageProvider.choices}
    if cfg.provider not in allowed:
        raise ValidationError(_("Unknown storage provider."))
    # policy reserved for future: e.g. only LOCAL unless enterprise flag
    _ = policy


def validate_expiry_consistency(doc: Document) -> None:
    """Expiry must not precede upload; retention should cover expiry when both set."""
    if doc.expires_at and doc.uploaded_at and doc.expires_at < doc.uploaded_at:
        raise ValidationError(_("Expiry cannot be before upload time."))


def log_audit_event(
    *,
    document: Document,
    using: str,
    action: str,
    message: str,
    actor_id: int | None = None,
    payload: dict | None = None,
) -> None:
    DocumentAuditEvent.objects.using(using).create(
        document=document,
        action=action,
        message=message[:500],
        payload=payload,
        actor_id=actor_id,
    )


def log_compliance_notes(
    *,
    document: Document,
    using: str,
    warnings: list[str],
    actor_id: int | None,
) -> None:
    if not warnings:
        return
    log_audit_event(
        document=document,
        using=using,
        action=DocumentAuditEvent.Action.COMPLIANCE,
        message="Compliance check: " + ", ".join(warnings),
        actor_id=actor_id,
        payload={"warnings": warnings},
    )
