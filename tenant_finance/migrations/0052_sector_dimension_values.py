from django.db import migrations


def seed_sector_dimension_values(apps, schema_editor):
    from django.db import DatabaseError

    db = schema_editor.connection.alias
    FinancialDimension = apps.get_model("tenant_finance", "FinancialDimension")
    FinancialDimensionValue = apps.get_model("tenant_finance", "FinancialDimensionValue")
    try:
        existing_tables = set(schema_editor.connection.introspection.table_names())
        if (
            FinancialDimension._meta.db_table not in existing_tables
            or FinancialDimensionValue._meta.db_table not in existing_tables
        ):
            return

        sector_dim, _ = FinancialDimension.objects.using(db).get_or_create(
            dimension_code="SECTOR",
            defaults={
                "dimension_name": "Program sector",
                "dimension_type": "classification",
                "description": "Program sector classification values.",
                "status": "active",
            },
        )

        defaults = [
            ("SEC-01", "Health"),
            ("SEC-02", "WASH"),
            ("SEC-03", "Education"),
            ("SEC-04", "Protection"),
            ("SEC-05", "Nutrition"),
            ("SEC-06", "Livelihood"),
            ("SEC-07", "Food Security"),
            ("SEC-08", "Shelter"),
            ("SEC-09", "GBV"),
            ("SEC-10", "Child Protection"),
            ("SEC-11", "Governance"),
            ("SEC-12", "Capacity building"),
            ("SEC-13", "Multi-sector"),
            ("SEC-14", "Other"),
        ]
        sid = sector_dim.pk
        for code, name in defaults:
            FinancialDimensionValue.objects.using(db).get_or_create(
                dimension_id=sid,
                code=code,
                defaults={"name": name, "description": "", "status": "active"},
            )
    except DatabaseError:
        return


class Migration(migrations.Migration):
    dependencies = [
        ("tenant_finance", "0051_financialdimensionvalue_program_values"),
    ]

    operations = [
        migrations.RunPython(seed_sector_dimension_values, migrations.RunPython.noop),
    ]
