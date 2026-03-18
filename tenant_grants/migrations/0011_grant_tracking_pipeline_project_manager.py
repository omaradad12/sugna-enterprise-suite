# Grant Tracking: Project model, pipeline stages, grant_manager, project FK, amount_awarded.

from django.db import migrations, models
import django.db.models.deletion


def map_old_pipeline_stages(apps, schema_editor):
    """Map old stage values to new; no-op if table does not exist (e.g. fresh tenant)."""
    try:
        GrantTracking = apps.get_model("tenant_grants", "GrantTracking")
        stage_map = {
            "proposal": "proposal_preparation",
            "submitted": "proposal_submitted",
        }
        for old, new in stage_map.items():
            GrantTracking.objects.filter(pipeline_stage=old).update(pipeline_stage=new)
    except Exception:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_grants", "0010_grant_tracking_pre_award_agreement_fields"),
        ("tenant_users", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(map_old_pipeline_stages, migrations.RunPython.noop),
        migrations.CreateModel(
            name="Project",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=50, unique=True)),
                ("name", models.CharField(max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.AddField(
            model_name="granttracking",
            name="grant_manager",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="grant_trackings_managed",
                to="tenant_users.tenantuser",
            ),
        ),
        migrations.AddField(
            model_name="granttracking",
            name="project",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="grant_trackings",
                to="tenant_grants.project",
            ),
        ),
        migrations.AddField(
            model_name="granttracking",
            name="amount_awarded",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Optional; cannot exceed amount requested unless override.",
                max_digits=14,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="granttracking",
            name="pipeline_stage",
            field=models.CharField(
                choices=[
                    ("opportunity", "Opportunity"),
                    ("concept_note", "Concept Note"),
                    ("proposal_preparation", "Proposal Preparation"),
                    ("proposal_submitted", "Proposal Submitted"),
                    ("under_review", "Under Review"),
                    ("clarification_requested", "Clarification Requested"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                    ("cancelled", "Cancelled"),
                ],
                db_index=True,
                default="opportunity",
                max_length=30,
            ),
        ),
    ]
