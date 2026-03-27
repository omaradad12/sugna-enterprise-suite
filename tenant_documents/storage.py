"""
Storage abstraction for multi-provider backends (local, S3, Azure Blob, etc.).

Current implementation: Django default storage (local MEDIA_ROOT). Subclasses
can be wired via StorageProviderConfig without changing Document models.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from django.core.files.storage import default_storage


@runtime_checkable
class TenantStorageBackend(Protocol):
    """Contract for per-tenant file backends."""

    @property
    def provider_code(self) -> str: ...

    def django_storage(self):
        """Return a django.core.files.storage.Storage instance."""
        ...


class LocalDjangoMediaBackend:
    """Local filesystem storage using Django media (default)."""

    provider_code = "local"

    def __init__(self, storage=None):
        self._storage = storage or default_storage

    def django_storage(self):
        return self._storage


def get_backend_for_provider(provider_code: str) -> TenantStorageBackend:
    """
    Factory for storage backends. Extend with S3/Azure/etc. when credentials exist.
    """
    code = (provider_code or "local").strip().lower()
    if code in ("", "local", "django", "filesystem"):
        return LocalDjangoMediaBackend()
    # Future: map to custom S3/Azure storages from django-storages
    return LocalDjangoMediaBackend()
