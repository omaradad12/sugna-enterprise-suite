from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0029_projectdimensionmapping_dynamic_fields"),
        ("tenant_grants", "0023_project_grant_period_extensions"),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentNumberLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("value", models.CharField(db_index=True, max_length=120, unique=True)),
                ("seq", models.PositiveIntegerField()),
                ("period_key", models.CharField(db_index=True, max_length=20)),
                ("document_type", models.CharField(db_index=True, max_length=40)),
                ("scope", models.CharField(db_index=True, max_length=20)),
                ("generated_at", models.DateTimeField(auto_now_add=True)),
                ("grant", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="tenant_grants.grant")),
                ("project", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="tenant_grants.project")),
                ("series", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="generated_numbers", to="tenant_finance.documentseries")),
            ],
            options={"ordering": ["-generated_at"]},
        ),
    ]

