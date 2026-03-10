# Generated for Sugna Enterprise Suite

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0003_tenant_domains_and_db_connection"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="brand_logo_url",
            field=models.URLField(
                blank=True,
                help_text="Public URL of the tenant logo for login screens.",
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="brand_primary_color",
            field=models.CharField(
                blank=True,
                help_text="Primary brand color (hex) used on buttons and accents.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="brand_background_color",
            field=models.CharField(
                blank=True,
                help_text="Background color (hex) for tenant login window.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="brand_login_title",
            field=models.CharField(
                blank=True,
                help_text="Custom title on login page (defaults to 'Sign in').",
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="brand_login_subtitle",
            field=models.CharField(
                blank=True,
                help_text="Custom subtitle on login page beneath the title.",
                max_length=255,
            ),
        ),
    ]

