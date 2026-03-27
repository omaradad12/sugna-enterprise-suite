from __future__ import annotations

from django.db.models.signals import post_delete, post_save

from tenant_documents.services.sync import sync_journal_attachment_to_document


def connect_signals() -> None:
    from tenant_finance.models import JournalEntry, JournalEntryAttachment

    post_save.connect(
        _sync_dm_on_journal_attachment_save,
        sender=JournalEntryAttachment,
        dispatch_uid="tenant_documents.sync_journal_attachment_save",
    )
    post_delete.connect(
        _delete_dm_on_journal_attachment_delete,
        sender=JournalEntryAttachment,
        dispatch_uid="tenant_documents.delete_journal_attachment",
    )
    post_save.connect(
        _sync_dm_on_journal_entry_save,
        sender=JournalEntry,
        dispatch_uid="tenant_documents.sync_journal_entry_save",
    )


def _sync_dm_on_journal_attachment_save(sender, instance, **kwargs):
    db = getattr(instance._state, "db", None) or "default"
    sync_journal_attachment_to_document(instance, using=db)


def _delete_dm_on_journal_attachment_delete(sender, instance, **kwargs):
    from tenant_documents.models import Document

    db = getattr(instance._state, "db", None) or "default"
    Document.objects.using(db).filter(source_journal_attachment_id=instance.pk).delete()


def _sync_dm_on_journal_entry_save(sender, instance, **kwargs):
    """When journal status changes, attachment rows may be updated via QuerySet.update — resync DM."""
    from tenant_finance.models import JournalEntryAttachment

    db = getattr(instance._state, "db", None) or "default"
    for att in JournalEntryAttachment.objects.using(db).filter(entry_id=instance.id):
        sync_journal_attachment_to_document(att, using=db)
