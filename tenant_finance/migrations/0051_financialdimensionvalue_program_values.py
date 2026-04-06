from django.db import migrations, models
import django.db.models.deletion


def seed_prog_dimension_values(apps, schema_editor):
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

        prog_dim, _ = FinancialDimension.objects.using(db).get_or_create(
            dimension_code="PROG",
            defaults={
                "dimension_name": "Program",
                "dimension_type": "program",
                "description": "Program dimension for funding/program categories.",
                "status": "active",
            },
        )

        defaults = [
            ("PRG-01", "Project grant"),
            ("PRG-02", "Core / institutional"),
            ("PRG-03", "Emergency"),
            ("PRG-04", "Institutional"),
            ("PRG-05", "Other"),
        ]
        # Use dimension_id only: assigning dimension=prog_dim triggers router/FK checks when
        # tenant context is unset during migrate --database=<tenant_alias>.
        pid = prog_dim.pk
        for code, name in defaults:
            FinancialDimensionValue.objects.using(db).get_or_create(
                dimension_id=pid,
                code=code,
                defaults={
                    "name": name,
                    "description": "",
                    "status": "active",
                },
            )
    except DatabaseError:
        # Some legacy tenant DBs may not yet have base finance setup tables.
        return


class Migration(migrations.Migration):
    dependencies = [
        ("tenant_finance", "0050_journalentry_receipt_stream"),
    ]

    operations = [
        migrations.CreateModel(
            name="FinancialDimensionValue",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=30)),
                ("name", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("active", "Active"), ("inactive", "Inactive")], default="active", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="tenant_users.tenantuser",
                    ),
                ),
                (
                    "dimension",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="values",
                        to="tenant_finance.financialdimension",
                    ),
                ),
            ],
            options={
                "ordering": ["dimension__dimension_code", "code"],
            },
        ),
        migrations.AddConstraint(
            model_name="financialdimensionvalue",
            constraint=models.UniqueConstraint(
                fields=("dimension", "code"),
                name="uq_fin_dimension_value_code_per_dimension",
            ),
        ),
        migrations.RunPython(seed_prog_dimension_values, migrations.RunPython.noop),
    ]
