# Generated for Sugna Enterprise Suite

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0002_tenant_status_and_plan"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="db_name",
            field=models.CharField(blank=True, help_text="Database name for this tenant (isolated DB).", max_length=128),
        ),
        migrations.AddField(
            model_name="tenant",
            name="db_user",
            field=models.CharField(blank=True, help_text="Database user for this tenant (least privilege).", max_length=128),
        ),
        migrations.AddField(
            model_name="tenant",
            name="db_password",
            field=models.CharField(blank=True, help_text="Database password for this tenant.", max_length=256),
        ),
        migrations.AddField(
            model_name="tenant",
            name="db_host",
            field=models.CharField(blank=True, help_text="Database host for this tenant.", max_length=255),
        ),
        migrations.AddField(
            model_name="tenant",
            name="db_port",
            field=models.CharField(blank=True, help_text="Database port for this tenant.", max_length=10),
        ),
        migrations.CreateModel(
            name="TenantDomain",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("domain", models.CharField(max_length=255, unique=True)),
                ("is_primary", models.BooleanField(default=False)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "tenant",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="domains", to="tenants.tenant"),
                ),
            ],
            options={"ordering": ["domain"]},
        ),
    ]

