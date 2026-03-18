from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0023_transactionreversalrule_extensions"),
    ]

    operations = [
        migrations.AddField(
            model_name="audittrailsetting",
            name="retention_policy",
            field=models.CharField(
                choices=[
                    ("30", "30 days"),
                    ("90", "90 days"),
                    ("180", "180 days"),
                    ("365", "1 year"),
                    ("730", "2 years"),
                    ("custom", "Custom"),
                ],
                default="365",
                help_text="High-level retention policy; Custom uses the Retention days value.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="audittrailsetting",
            name="auto_archive",
            field=models.BooleanField(
                default=True,
                help_text="If enabled, older audit logs are auto-archived according to the retention policy.",
            ),
        ),
        migrations.AddField(
            model_name="audittrailsetting",
            name="track_field_level_changes",
            field=models.BooleanField(
                default=True,
                help_text="Track field-level before/after changes for key financial and user records.",
            ),
        ),
        migrations.AddField(
            model_name="audittrailsetting",
            name="strict_posting_protection",
            field=models.BooleanField(
                default=True,
                help_text="If enabled, posted journals are locked (no edit/delete) and must be corrected via reversals.",
            ),
        ),
        migrations.AddField(
            model_name="audittrailsetting",
            name="risk_classification",
            field=models.CharField(
                choices=[("low", "Low"), ("medium", "Medium"), ("high", "High")],
                default="medium",
                help_text="Default classification applied to flagged audit events for reporting and escalation.",
                max_length=20,
            ),
        ),
    ]

