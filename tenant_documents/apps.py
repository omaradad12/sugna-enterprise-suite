from __future__ import annotations

from django.apps import AppConfig


class TenantDocumentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tenant_documents"
    verbose_name = "Document Management"

    def ready(self) -> None:
        from tenant_documents.signals import connect_signals

        connect_signals()
