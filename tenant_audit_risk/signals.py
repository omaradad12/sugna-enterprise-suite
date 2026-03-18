"""
Signals to run Fraud Detection Engine when transactions are posted,
and to delete temporary screening files when an investigation case is closed.
Connection is done in AppConfig.ready() to avoid circular imports.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver


def on_investigation_case_closed(sender, instance, **kwargs):
    """When an InvestigationCase is saved with status=closed, delete temp screening files for linked sessions."""
    if getattr(instance, "status", None) != "closed":
        return
    using = getattr(instance._state, "db", None) or "default"
    if using == "default":
        return
    try:
        from tenant_audit_risk.models import AuditScreeningSession, ScreeningUploadFile
        from tenant_audit_risk.services.screening_storage import delete_session_files

        sessions = AuditScreeningSession.objects.using(using).filter(
            case_id=instance.pk,
            status=AuditScreeningSession.Status.ACTIVE,
        )
        for session in sessions:
            delete_session_files(session.id)
            ScreeningUploadFile.objects.using(using).filter(session=session).delete()
            session.status = AuditScreeningSession.Status.CLOSED
            session.save(using=using)
    except Exception:
        pass


def on_journal_entry_posted(sender, instance, created, **kwargs):
    """When a JournalEntry is saved with status=posted, run fraud detection."""
    if getattr(instance, "status", None) != "posted":
        return
    if not getattr(instance, "posted_at", None):
        return
    # Only run when we have a tenant DB (instance was saved to a tenant DB)
    using = getattr(instance._state, "db", None) or "default"
    if using == "default":
        return
    try:
        from tenant_audit_risk.services.fraud_detection_engine import evaluate_journal_entry
        evaluate_journal_entry(instance.pk, using)
    except Exception:
        pass  # Don't block posting on engine failure
