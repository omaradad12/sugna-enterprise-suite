# Operational project on journal header + backfill from grant (duplicate detection).

from django.db import migrations, models
import django.db.models.deletion


def backfill_journalentry_project(apps, schema_editor):
    JournalEntry = apps.get_model("tenant_finance", "JournalEntry")
    Grant = apps.get_model("tenant_grants", "Grant")
    db = schema_editor.connection.alias
    for je in (
        JournalEntry.objects.using(db)
        .filter(project_id__isnull=True)
        .exclude(grant_id__isnull=True)
        .only("id", "grant_id")
        .iterator(chunk_size=500)
    ):
        pid = Grant.objects.using(db).filter(pk=je.grant_id).values_list("project_id", flat=True).first()
        if pid:
            JournalEntry.objects.using(db).filter(pk=je.pk).update(project_id=pid)


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0057_fiscalperiod_status_locked"),
        ("tenant_grants", "0043_budgetline_flat_budget_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="journalentry",
            name="project",
            field=models.ForeignKey(
                blank=True,
                help_text="Operational project for duplicate detection and reporting (may mirror grant.project).",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="tagged_journal_entries",
                to="tenant_grants.project",
            ),
        ),
        migrations.RunPython(backfill_journalentry_project, migrations.RunPython.noop),
    ]
