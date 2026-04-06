from __future__ import annotations


class TenantFinanceInitError(Exception):
    """
    Raised when baseline finance / setup data cannot be written to the tenant database.

    Carries structured context so provisioning can persist a clear message (model + database)
    without weakening the database router.
    """

    def __init__(
        self,
        message: str,
        *,
        model_label: str | None = None,
        database: str | None = None,
    ) -> None:
        super().__init__(message)
        self.model_label = model_label
        self.database = database

    def detail(self) -> str:
        parts = [str(self)]
        if self.model_label:
            parts.append(f"model={self.model_label}")
        if self.database:
            parts.append(f"database={self.database}")
        return " ".join(parts)
