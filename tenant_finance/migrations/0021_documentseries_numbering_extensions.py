from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Align tenant_finance_documentseries table with the current DocumentSeries model
    by adding numbering-related fields and status/notes.

    This migration is intentionally conservative and only adds columns/constraints
    that are missing from the original 0005 schema. Existing data is preserved.
    """

    dependencies = [
        ("tenant_finance", "0020_add_fiscal_year_if_missing"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentseries",
            name="number_format",
            field=models.CharField(
                max_length=80,
                default="{prefix}{year}-{seq:05d}",
                help_text=(
                    "Python-style format string using prefix, year, seq. "
                    "Example: 'PV-{year}-{seq:05d}'"
                ),
            ),
        ),
        migrations.AddField(
            model_name="documentseries",
            name="reset_frequency",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("yearly", "Yearly"),
                    ("monthly", "Monthly"),
                    ("never", "Never"),
                ],
                default="yearly",
            ),
        ),
        migrations.AddField(
            model_name="documentseries",
            name="status",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("active", "Active"),
                    ("inactive", "Inactive"),
                ],
                default="active",
                db_index=True,
            ),
        ),
        migrations.AddField(
            model_name="documentseries",
            name="notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddConstraint(
            model_name="documentseries",
            constraint=models.UniqueConstraint(
                fields=("document_type", "fiscal_year", "prefix"),
                name="uniq_documentseries_type_year_prefix",
            ),
        ),
    ]

