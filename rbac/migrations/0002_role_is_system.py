from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="role",
            name="is_system",
            field=models.BooleanField(
                default=False,
                db_index=True,
                help_text="Protected system role (cannot be edited or deleted by tenants).",
            ),
        ),
    ]

