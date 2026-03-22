"""
Helpers for idempotent tenant_finance migrations (avoid duplicate-column errors).

DefaultAccountMapping.transaction_type was created in 0005; 0019 must not ADD it again.

Leading underscore: Django skips this module when loading migrations (see MigrationLoader).
"""

from __future__ import annotations

from django.db import models


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


def ensure_defaultaccountmapping_transaction_type(apps, schema_editor) -> None:
    """
    Add DefaultAccountMapping.transaction_type only if the column is missing.

    0005 CreateModel already includes transaction_type; 0019 AddField would duplicate it.
    """
    Model = apps.get_model("tenant_finance", "DefaultAccountMapping")
    table = Model._meta.db_table
    if column_exists(schema_editor, table, "transaction_type"):
        return
    field = models.CharField(
        max_length=40,
        choices=[
            ("receipt", "Receipt"),
            ("payment", "Payment"),
            ("journal", "Journal"),
            ("transfer", "Transfer"),
        ],
        default="receipt",
    )
    field.set_attributes_from_name("transaction_type")
    schema_editor.add_field(Model, field)


def noop_reverse(apps, schema_editor) -> None:
    pass
