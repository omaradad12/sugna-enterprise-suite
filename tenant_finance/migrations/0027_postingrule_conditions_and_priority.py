from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0026_numbering_schema_safety_net"),
    ]

    operations = [
        migrations.AddField(
            model_name="postingrule",
            name="priority",
            field=models.PositiveSmallIntegerField(
                default=100,
                help_text="Lower numbers are evaluated first (higher precedence).",
            ),
        ),
        migrations.AddField(
            model_name="postingrule",
            name="conditions",
            field=models.JSONField(
                default=dict,
                blank=True,
                help_text="Optional conditions for rule matching (e.g. project_id, grant_id, donor_id, min_amount, max_amount).",
            ),
        ),
    ]

