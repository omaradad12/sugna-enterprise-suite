"""
Detect tenant DB schema drift vs. Django models (e.g. migrations not applied on a tenant DB).
"""
from __future__ import annotations

from typing import FrozenSet

from django.db import connections


def _table_column_names(connection, table_name: str) -> FrozenSet[str]:
    with connection.cursor() as cursor:
        desc = connection.introspection.get_table_description(cursor, table_name)
    # Normalize for backends that return mixed case (e.g. some SQL Server configs).
    return frozenset((d.name or "").lower() for d in desc)


def journalentry_has_0034_schema(using: str) -> bool:
    """True if JournalEntry table has columns added in 0034_journalentry_posting_metadata."""
    from tenant_finance.models import JournalEntry

    table = JournalEntry._meta.db_table
    conn = connections[using]
    try:
        cols = _table_column_names(conn, table)
    except Exception:
        return False
    required = frozenset(
        {
            "posted_by_id",
            "is_system_generated",
            "source_document_no",
            "source_id",
            "source_type",
        }
    )  # lowercase keys — matches _table_column_names normalization
    return required.issubset(cols)


def journalentry_has_0040_adjusting_schema(using: str) -> bool:
    """True if JournalEntry has NGO adjusting fields (0040_adjusting_journal_ngo)."""
    from tenant_finance.models import JournalEntry

    table = JournalEntry._meta.db_table
    conn = connections[using]
    try:
        cols = _table_column_names(conn, table)
    except Exception:
        return False
    return "posting_date" in cols and "adjustment_type" in cols


def interfund_tables_present(using: str) -> bool:
    """
    True if InterFundTransfer + InterFundTransferRule tables exist (tenant_finance.0032+).
    """
    from tenant_finance.models import InterFundTransfer, InterFundTransferRule

    conn = connections[using]
    try:
        names = {t.lower() for t in conn.introspection.table_names()}
    except Exception:
        return False
    need = {
        InterFundTransfer._meta.db_table.lower(),
        InterFundTransferRule._meta.db_table.lower(),
    }
    return need.issubset(names)
