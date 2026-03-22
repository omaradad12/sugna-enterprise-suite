# Recurring journal: NGO template fields, line-level grant, status workflow

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


def forwards(apps, schema_editor):
    db = schema_editor.connection.alias
    RecurringJournal = apps.get_model("tenant_finance", "RecurringJournal")
    RecurringJournalLine = apps.get_model("tenant_finance", "RecurringJournalLine")
    today = django.utils.timezone.now().date()
    for rj in RecurringJournal.objects.using(db).all():
        memo = getattr(rj, "memo", "") or ""
        if not getattr(rj, "description", ""):
            rj.description = memo
        if not getattr(rj, "start_date", None):
            rj.start_date = rj.next_run_date or today
        if not getattr(rj, "status", ""):
            rj.status = "active" if getattr(rj, "is_active", True) else "paused"
        rj.save(using=db)
        gid = getattr(rj, "grant_id", None)
        if gid:
            for line in RecurringJournalLine.objects.using(db).filter(recurring_journal=rj):
                if getattr(line, "grant_id", None) is None:
                    line.grant_id = gid
                    line.save(using=db)


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0038_interfund_transfer_project_bank"),
        ("tenant_grants", "0023_project_grant_period_extensions"),
    ]

    operations = [
        migrations.AddField(
            model_name="recurringjournal",
            name="description",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="recurringjournal",
            name="start_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="recurringjournal",
            name="end_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="recurringjournal",
            name="status",
            field=models.CharField(
                choices=[("active", "Active"), ("paused", "Paused"), ("completed", "Completed")],
                db_index=True,
                default="active",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="recurringjournal",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name="recurringjournalline",
            name="grant",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="recurring_journal_lines",
                to="tenant_grants.grant",
            ),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(model_name="recurringjournal", name="grant"),
        migrations.RemoveField(model_name="recurringjournal", name="is_active"),
        migrations.RemoveField(model_name="recurringjournal", name="memo"),
        migrations.AlterField(
            model_name="recurringjournal",
            name="start_date",
            field=models.DateField(help_text="Schedule start; first run uses this date."),
        ),
    ]
