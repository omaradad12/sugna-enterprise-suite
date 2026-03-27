from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from tenant_documents.models import Document, DocumentAuditEvent, DocumentStatus, DocumentType
from tenant_documents.services.validation import (
    enrich_document_file_hash_and_retention,
    get_policy,
    log_audit_event,
    log_compliance_notes,
    validate_finance_link_completeness,
)

if TYPE_CHECKING:
    from tenant_finance.models import JournalEntry, JournalEntryAttachment


def _status_from_journal_entry(entry: "JournalEntry") -> tuple[str, bool]:
    """
    Map journal workflow to document status + lock flag.
    """
    from tenant_finance.models import JournalEntry as JE

    st = entry.status
    if st == JE.Status.DRAFT:
        return DocumentStatus.DRAFT, False
    if st == JE.Status.PENDING_APPROVAL:
        return DocumentStatus.PENDING_APPROVAL, False
    if st == JE.Status.APPROVED:
        return DocumentStatus.APPROVED, False
    if st == JE.Status.POSTED:
        return DocumentStatus.POSTED, True
    if st == JE.Status.REVERSED:
        return DocumentStatus.REVERSED, True
    return DocumentStatus.ARCHIVED, True


def sync_journal_attachment_to_document(
    attachment: "JournalEntryAttachment",
    *,
    using: str | None = None,
) -> Document | None:
    """
    Upsert a central Document row for a finance journal attachment (single file reference).
    """
    from tenant_finance.models import JournalEntryAttachment

    if not isinstance(attachment, JournalEntryAttachment):
        return None
    db = using or getattr(attachment._state, "db", None) or "default"
    if not attachment.entry_id:
        return None

    entry = attachment.entry
    status, locked = _status_from_journal_entry(entry)

    valid_types = {c for c, _ in DocumentType.choices}
    doc_type = (attachment.document_category or "").strip() or DocumentType.OTHER
    if doc_type not in valid_types:
        doc_type = DocumentType.OTHER

    policy = get_policy(db)

    def _write(doc: Document, *, created: bool, prev_status: str | None) -> Document:
        doc.file = attachment.file
        doc.original_filename = attachment.original_filename or ""
        doc.tenant_key = attachment.tenant or db
        doc.module = attachment.module
        doc.submodule = attachment.submodule
        doc.linked_record_type = attachment.linked_record_type or "journal_entry"
        doc.linked_record_id = attachment.linked_record_id or entry.id
        doc.voucher_number = attachment.voucher_number or ""
        doc.project_id = attachment.project_id
        doc.grant_id = attachment.grant_id
        doc.donor_id = attachment.donor_id
        doc.status = status
        doc.is_locked = locked
        doc.storage_provider = attachment.storage_provider or ""
        doc.uploaded_by_id = attachment.uploaded_by_id
        doc.document_type = doc_type
        doc.refresh_file_metadata()
        doc.save(using=db)
        enrich_document_file_hash_and_retention(doc, db, policy)
        doc.metadata_synced_at = timezone.now()
        doc.save(
            using=db,
            update_fields=["file_sha256", "size_bytes", "mime_type", "retention_until", "metadata_synced_at"],
        )
        if created:
            DocumentAuditEvent.objects.using(db).create(
                document=doc,
                action=DocumentAuditEvent.Action.CREATED,
                message="Registered from journal attachment (metadata, integrity hash, retention applied)",
                actor_id=attachment.uploaded_by_id,
                payload={"journal_entry_id": entry.id, "attachment_id": attachment.pk},
            )
        elif prev_status is not None and prev_status != status:
            DocumentAuditEvent.objects.using(db).create(
                document=doc,
                action=DocumentAuditEvent.Action.STATUS,
                message=f"Status synced from journal entry {entry.id}",
                payload={"from": prev_status, "to": status, "locked": locked},
                actor_id=attachment.uploaded_by_id,
            )
        warn_cat = policy.ngo_warn_missing_journal_document_category and not (
            attachment.document_category or ""
        ).strip()
        if warn_cat and created:
            log_audit_event(
                document=doc,
                using=db,
                action=DocumentAuditEvent.Action.COMPLIANCE,
                message="Journal attachment has no NGO document category (donor/audit classification).",
                actor_id=attachment.uploaded_by_id,
                payload={"journal_entry_id": entry.id},
            )
        comp = validate_finance_link_completeness(doc, policy, entry=entry)
        if created and comp:
            log_compliance_notes(document=doc, using=db, warnings=comp, actor_id=attachment.uploaded_by_id)
        return doc

    with transaction.atomic(using=db):
        existing = (
            Document.objects.using(db)
            .filter(source_journal_attachment_id=attachment.pk)
            .first()
        )
        if existing:
            prev = existing.status
            return _write(existing, created=False, prev_status=prev)
        doc = Document(source_journal_attachment=attachment)
        return _write(doc, created=True, prev_status=None)


def sync_all_journal_attachments(using: str) -> int:
    """Backfill: sync every JournalEntryAttachment in the tenant DB."""
    from tenant_finance.models import JournalEntryAttachment

    n = 0
    for att in JournalEntryAttachment.objects.using(using).iterator():
        sync_journal_attachment_to_document(att, using=using)
        n += 1
    return n
