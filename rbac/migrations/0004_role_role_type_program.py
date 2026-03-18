from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0003_role_role_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="role",
            name="role_type",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("financial", "Financial"),
                    ("operational", "Operational"),
                    ("program", "Program"),
                    ("admin", "Admin"),
                ],
                default="operational",
                db_index=True,
            ),
        ),
    ]

