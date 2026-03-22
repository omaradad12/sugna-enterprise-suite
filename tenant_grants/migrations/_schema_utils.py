"""
Idempotent migration helpers for tenant_grants (leading _: Django ignores this file).

Avoid DuplicateColumn when a tenant DB was partially migrated or columns were added manually.
"""

from __future__ import annotations


def column_exists(schema_editor, table_name: str, column_name: str) -> bool:
    """True if `column_name` exists on `table_name` for this connection."""
    connection = schema_editor.connection
    want = column_name.lower()
    with connection.cursor() as cursor:
        tables = connection.introspection.table_names(cursor)
        matched = None
        for t in tables:
            if t.lower() == table_name.lower():
                matched = t
                break
        if not matched:
            return False
        try:
            description = connection.introspection.get_table_description(cursor, matched)
        except Exception:
            return False
    for col in description:
        cname = col.name if hasattr(col, "name") else col[0]
        if cname.lower() == want:
            return True
    return False
