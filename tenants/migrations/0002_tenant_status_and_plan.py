# Generated for Sugna Enterprise Suite

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("trial", "Trial"),
                    ("pending", "Pending"),
                    ("suspended", "Suspended"),
                    ("expired", "Expired"),
                ],
                default="active",
                help_text="Display status for tenant lifecycle (Active, Trial, Pending, Suspended, Expired)",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="plan",
            field=models.CharField(blank=True, help_text="Subscription plan name", max_length=100),
        ),
        migrations.AddField(
            model_name="tenant",
            name="subscription_expiry",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="tenant",
            name="country",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="tenant",
            name="user_count",
            field=models.PositiveIntegerField(default=0, help_text="Number of users in this tenant"),
        ),
        migrations.AddField(
            model_name="tenant",
            name="storage_mb",
            field=models.PositiveIntegerField(default=0, help_text="Storage used in MB"),
        ),
    ]
