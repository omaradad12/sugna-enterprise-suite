import django.db.models.deletion
from django.db import migrations, models


def forwards_map_modality_values(apps, schema_editor):
    FundingSource = apps.get_model("tenant_grants", "FundingSource")
    db = schema_editor.connection.alias
    MAP = {
        "grant": "mixed_modality",
        "donation": "advance",
        "contribution": "cost_share",
    }
    for fs in FundingSource.objects.using(db).all():
        cur = getattr(fs, "modality_type", None) or ""
        if cur in MAP:
            FundingSource.objects.using(db).filter(pk=fs.pk).update(modality_type=MAP[cur])


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_grants", "0033_donor_validation_audit"),
    ]

    operations = [
        migrations.RenameField(
            model_name="fundingsource",
            old_name="funding_type",
            new_name="modality_type",
        ),
        migrations.RunPython(forwards_map_modality_values, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="fundingsource",
            name="modality_type",
            field=models.CharField(
                choices=[
                    ("advance", "Advance"),
                    ("instalment", "Instalment"),
                    ("reimbursement", "Reimbursement"),
                    ("advance_with_retention", "Advance with retention"),
                    ("milestone_based", "Milestone based"),
                    ("cost_share", "Cost share"),
                    ("mixed_modality", "Mixed modality"),
                ],
                db_index=True,
                default="mixed_modality",
                help_text="How payments are structured (advance, reimbursement, retention, etc.).",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="fundingsource",
            name="retention_percentage",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Optional retention held back until conditions are met (0–100).",
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="fundingsource",
            name="allow_instalments",
            field=models.BooleanField(
                default=False,
                help_text="Whether multiple payment tranches are allowed under this modality.",
            ),
        ),
        migrations.AddField(
            model_name="fundingsource",
            name="requires_reporting_before_next_payment",
            field=models.BooleanField(
                default=False,
                help_text="If true, narrative/financial reporting gates the next instalment.",
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="funding_modality",
            field=models.ForeignKey(
                blank=True,
                help_text="Payment modality: receivable schedule, retention, reimbursement controls.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="projects",
                to="tenant_grants.fundingsource",
            ),
        ),
        migrations.AddField(
            model_name="grant",
            name="funding_modality",
            field=models.ForeignKey(
                blank=True,
                help_text="Payment modality for this agreement; syncs funding method rules when set.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="grants",
                to="tenant_grants.fundingsource",
            ),
        ),
    ]
