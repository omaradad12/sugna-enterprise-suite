# Generated manually for enterprise reporting deadlines.

from django.db import migrations, models
import django.db.models.deletion


def forwards_status(apps, schema_editor):
    ReportingDeadline = apps.get_model("tenant_grants", "ReportingDeadline")
    db = schema_editor.connection.alias
    ReportingDeadline.objects.using(db).filter(status__in=["pending", "overdue"]).update(
        status="open"
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_grants", "0027_project_budget_workplan_activity_link"),
        ("tenant_users", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportingdeadline",
            name="priority",
            field=models.CharField(
                choices=[
                    ("low", "Low"),
                    ("normal", "Normal"),
                    ("high", "High"),
                    ("critical", "Critical"),
                ],
                db_index=True,
                default="normal",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="reportingdeadline",
            name="project",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="reporting_deadlines",
                to="tenant_grants.project",
            ),
        ),
        migrations.AddField(
            model_name="reportingdeadline",
            name="reminder_days_before",
            field=models.PositiveSmallIntegerField(
                default=7,
                help_text="Within this many days before the deadline, status shows as Due (if not submitted).",
            ),
        ),
        migrations.AddField(
            model_name="reportingdeadline",
            name="reporting_period_from",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="reportingdeadline",
            name="reporting_period_to",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="reportingdeadline",
            name="reviewer_user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="reporting_deadlines_reviewer",
                to="tenant_users.tenantuser",
            ),
        ),
        migrations.AddField(
            model_name="reportingdeadline",
            name="responsible_user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="reporting_deadlines_responsible",
                to="tenant_users.tenantuser",
            ),
        ),
        migrations.AddField(
            model_name="reportingdeadline",
            name="submitted_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="reportingdeadline",
            name="deadline_date",
            field=models.DateField(db_index=True),
        ),
        migrations.RunPython(forwards_status, noop_reverse),
        migrations.AlterField(
            model_name="reportingdeadline",
            name="status",
            field=models.CharField(
                choices=[("open", "Open"), ("submitted", "Submitted")],
                db_index=True,
                default="open",
                max_length=20,
            ),
        ),
    ]
