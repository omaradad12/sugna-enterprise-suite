# NGO adjusting journal: posting date, adjustment type, donor, line-level grant

from django.db import migrations, models
import django.db.models.deletion


def backfill_posting_dates(apps, schema_editor):
    JournalEntry = apps.get_model("tenant_finance", "JournalEntry")
    db = schema_editor.connection.alias
    for je in JournalEntry.objects.using(db).filter(posting_date__isnull=True).iterator(chunk_size=500):
        je.posting_date = je.entry_date
        je.save(using=db, update_fields=["posting_date"])


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0039_recurring_journal_ngo"),
        ("tenant_grants", "0023_project_grant_period_extensions"),
    ]

    operations = [
        migrations.AddField(
            model_name="journalentry",
            name="posting_date",
            field=models.DateField(
                blank=True,
                null=True,
                help_text="GL posting date (drives fiscal period for posting). Defaults to journal date when omitted.",
            ),
        ),
        migrations.AddField(
            model_name="journalentry",
            name="adjustment_type",
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=40,
                help_text="NGO adjusting entry classification (accrual, reclassification, etc.).",
            ),
        ),
        migrations.AddField(
            model_name="journalentry",
            name="donor",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="journal_entries",
                to="tenant_grants.donor",
            ),
        ),
        migrations.AddField(
            model_name="journalline",
            name="grant",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="journal_lines",
                to="tenant_grants.grant",
            ),
        ),
        migrations.RunPython(backfill_posting_dates, migrations.RunPython.noop),
    ]
