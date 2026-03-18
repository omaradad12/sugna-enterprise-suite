# Pre-award Grant Tracking (pipeline) and post-award Grant Agreement link + agreement fields.

from django.db import migrations, models
import django.db.models.deletion


def generate_tracking_codes(apps, schema_editor):
    """Ensure existing data: not needed for new model; Grant gets new fields only."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_grants", "0009_grant_tracking_fields_and_documents"),
    ]

    operations = [
        migrations.CreateModel(
            name="GrantTracking",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=50, unique=True)),
                ("title", models.CharField(max_length=255)),
                (
                    "pipeline_stage",
                    models.CharField(
                        choices=[
                            ("opportunity", "Opportunity"),
                            ("proposal", "Proposal"),
                            ("submitted", "Submitted"),
                            ("under_review", "Under review"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                        ],
                        db_index=True,
                        default="opportunity",
                        max_length=20,
                    ),
                ),
                (
                    "grant_type",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("federal", "Federal Government"),
                            ("state_local", "State / Local Gov't"),
                            ("association", "Association"),
                            ("corporate", "Corporate Foundation"),
                            ("private", "Private Foundation"),
                            ("other", "Other"),
                        ],
                        default="other",
                        max_length=20,
                    ),
                ),
                (
                    "priority",
                    models.CharField(
                        blank=True,
                        choices=[("low", "Low"), ("medium", "Medium"), ("high", "High")],
                        default="medium",
                        max_length=20,
                    ),
                ),
                ("submission_deadline", models.DateField(blank=True, null=True)),
                ("date_submitted", models.DateField(blank=True, null=True)),
                ("project_name", models.CharField(blank=True, max_length=255)),
                (
                    "amount_requested",
                    models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
                ),
                ("grant_owner", models.CharField(blank=True, max_length=120)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "donor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="grant_trackings",
                        to="tenant_grants.donor",
                    ),
                ),
            ],
            options={
                "ordering": ["-updated_at", "-created_at"],
                "verbose_name": "Grant tracking (pre-award)",
                "verbose_name_plural": "Grant trackings (pre-award)",
            },
        ),
        migrations.CreateModel(
            name="GrantTrackingDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(upload_to="grants/tracking_docs/%Y/%m/")),
                ("original_filename", models.CharField(blank=True, max_length=255)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "tracking",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="documents",
                        to="tenant_grants.granttracking",
                    ),
                ),
            ],
            options={
                "ordering": ["-uploaded_at"],
            },
        ),
        migrations.AddField(
            model_name="grant",
            name="source_tracking",
            field=models.OneToOneField(
                blank=True,
                help_text="Approved tracking record this agreement was created from.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="grant_agreement",
                to="tenant_grants.granttracking",
            ),
        ),
        migrations.AddField(
            model_name="grant",
            name="signed_date",
            field=models.DateField(blank=True, help_text="Date the agreement was signed.", null=True),
        ),
        migrations.AddField(
            model_name="grant",
            name="reporting_rules",
            field=models.TextField(
                blank=True,
                help_text="Donor reporting requirements summary for this agreement.",
            ),
        ),
        migrations.AddField(
            model_name="grant",
            name="donor_restrictions",
            field=models.TextField(
                blank=True,
                help_text="Donor conditions and restrictions for this agreement.",
            ),
        ),
        migrations.AddField(
            model_name="grant",
            name="signed_contract_document",
            field=models.FileField(blank=True, null=True, upload_to="grants/agreement_contracts/%Y/%m/"),
        ),
    ]
