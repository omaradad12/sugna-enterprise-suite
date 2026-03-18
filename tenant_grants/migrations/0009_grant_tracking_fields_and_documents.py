# Generated migration for Grant Tracking / Create Grant form fields and document uploads.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_grants", "0008_alter_budgettemplate_id_alter_budgettemplateline_id_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="grant",
            name="grant_type",
            field=models.CharField(
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
        migrations.AddField(
            model_name="grant",
            name="priority",
            field=models.CharField(
                blank=True,
                choices=[("low", "Low"), ("medium", "Medium"), ("high", "High")],
                default="medium",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="grant",
            name="submission_deadline",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="grant",
            name="date_submitted",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="grant",
            name="project_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="grant",
            name="amount_requested",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=14, null=True
            ),
        ),
        migrations.AddField(
            model_name="grant",
            name="notes",
            field=models.TextField(blank=True),
        ),
        migrations.CreateModel(
            name="GrantDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(upload_to="grants/documents/%Y/%m/")),
                ("original_filename", models.CharField(blank=True, max_length=255)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "grant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="documents",
                        to="tenant_grants.grant",
                    ),
                ),
            ],
            options={
                "ordering": ["-uploaded_at"],
            },
        ),
    ]
