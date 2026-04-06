# Generated manually for trial management (Platform Console).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0011_tenant_branding_text_on_colors"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="trial_started_at",
            field=models.DateField(
                blank=True,
                help_text="When the trial period started (optional; UI falls back to tenant created date).",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="trial_converted_at",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                help_text="Set when the tenant converts from trial to a paid subscription.",
                null=True,
            ),
        ),
    ]
