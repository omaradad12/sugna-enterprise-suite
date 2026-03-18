# Grant Workplan: WorkplanActivity model for activities linked to grants.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_grants", "0012_donor_register_master_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkplanActivity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("workplan_code", models.CharField(blank=True, help_text="Auto-generated Workplan ID (e.g. WP-00001).", max_length=30, unique=True)),
                ("activity", models.CharField(max_length=255)),
                ("component_output", models.CharField(blank=True, max_length=255)),
                ("responsible_department", models.CharField(blank=True, max_length=120)),
                ("responsible_staff", models.CharField(blank=True, max_length=120)),
                ("start_date", models.DateField(blank=True, null=True)),
                ("end_date", models.DateField(blank=True, null=True)),
                ("budget_amount", models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=14, null=True)),
                ("pr_number", models.CharField(blank=True, max_length=80)),
                ("pr_status", models.CharField(blank=True, choices=[("pending", "Pending"), ("submitted", "Submitted"), ("approved", "Approved"), ("ordered", "Ordered"), ("received", "Received"), ("closed", "Closed"), ("none", "—")], default="none", max_length=20)),
                ("activity_status", models.CharField(choices=[("planned", "Planned"), ("in_progress", "In Progress"), ("completed", "Completed")], default="planned", max_length=20)),
                ("workplan_status", models.CharField(choices=[("draft", "Draft"), ("active", "Active"), ("completed", "Completed")], default="active", max_length=20)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("donor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="workplan_activities", to="tenant_grants.donor")),
                ("grant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="workplan_activities", to="tenant_grants.grant")),
            ],
            options={
                "ordering": ["-created_at"],
                "verbose_name": "Workplan activity",
                "verbose_name_plural": "Workplan activities",
            },
        ),
    ]
