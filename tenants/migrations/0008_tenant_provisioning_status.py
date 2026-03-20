# Tenant provisioning tracking fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0007_subscriptionplan"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="provisioned_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When provisioning_status last reached success.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="provisioning_error",
            field=models.TextField(
                blank=True,
                help_text="Last provisioning failure message (cleared on success).",
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="provisioning_status",
            field=models.CharField(
                choices=[
                    ("not_started", "Not started"),
                    ("in_progress", "In progress"),
                    ("success", "Success"),
                    ("failed", "Failed"),
                ],
                db_index=True,
                default="not_started",
                help_text="Tracks automatic provisioning pipeline; inspect provisioning_error if failed.",
                max_length=20,
            ),
        ),
    ]
