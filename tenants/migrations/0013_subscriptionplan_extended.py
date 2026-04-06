# Extended subscription plan fields (Platform Console).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0012_tenant_trial_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscriptionplan",
            name="billing_cycle",
            field=models.CharField(
                choices=[
                    ("monthly", "Monthly"),
                    ("quarterly", "Quarterly"),
                    ("yearly", "Yearly"),
                    ("one_time", "One-time"),
                ],
                default="monthly",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="currency",
            field=models.CharField(default="USD", max_length=3),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="is_archived",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="is_draft",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="max_organizations",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Included tenant organizations (optional cap).",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="max_storage_mb",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Leave empty for unlimited.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="max_users",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Leave empty for unlimited.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="price",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="trial_duration_days",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="Trial length in days when trial is enabled.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="trial_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="visibility",
            field=models.CharField(
                choices=[("public", "Public"), ("internal", "Internal")],
                db_index=True,
                default="public",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="included_modules",
            field=models.ManyToManyField(
                blank=True,
                related_name="subscription_plans",
                to="tenants.module",
            ),
        ),
    ]
