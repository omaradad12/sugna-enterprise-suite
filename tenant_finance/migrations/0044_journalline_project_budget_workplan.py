import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_grants", "0027_project_budget_workplan_activity_link"),
        ("tenant_finance", "0043_project_master_registry_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="journalline",
            name="project_budget_line",
            field=models.ForeignKey(
                blank=True,
                help_text="Project budget line for expense tracking (NGO activity-based budgeting).",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="journal_lines",
                to="tenant_grants.projectbudgetline",
            ),
        ),
        migrations.AddField(
            model_name="journalline",
            name="workplan_activity",
            field=models.ForeignKey(
                blank=True,
                help_text="Grant workplan activity for expense tagging.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="journal_lines",
                to="tenant_grants.workplanactivity",
            ),
        ),
        migrations.AddIndex(
            model_name="journalline",
            index=models.Index(fields=["project_budget_line"], name="journalline_pbl_idx"),
        ),
        migrations.AddIndex(
            model_name="journalline",
            index=models.Index(fields=["workplan_activity"], name="journalline_wa_idx"),
        ),
    ]
