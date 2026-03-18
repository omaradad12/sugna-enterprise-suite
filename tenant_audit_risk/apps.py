from django.apps import AppConfig


class TenantAuditRiskConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tenant_audit_risk"
    verbose_name = "Audit & Risk Management"

    def ready(self):
        from django.db.models.signals import post_save
        from tenant_audit_risk.signals import on_investigation_case_closed, on_journal_entry_posted
        try:
            from tenant_finance.models import JournalEntry
            post_save.connect(on_journal_entry_posted, sender=JournalEntry)
        except Exception:
            pass
        try:
            from tenant_audit_risk.models import InvestigationCase
            post_save.connect(on_investigation_case_closed, sender=InvestigationCase)
        except Exception:
            pass
