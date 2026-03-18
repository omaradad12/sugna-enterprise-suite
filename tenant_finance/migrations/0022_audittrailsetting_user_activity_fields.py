from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0021_documentseries_numbering_extensions"),
    ]

    operations = [
        # User activity tracking fields
        migrations.AddField(
            model_name="audittrailsetting",
            name="track_logins",
            field=models.BooleanField(
                default=False,
                help_text="Track user logins and logouts.",
            ),
        ),
        migrations.AddField(
            model_name="audittrailsetting",
            name="track_failed_logins",
            field=models.BooleanField(
                default=False,
                help_text="Track failed login attempts.",
            ),
        ),
        migrations.AddField(
            model_name="audittrailsetting",
            name="track_user_changes",
            field=models.BooleanField(
                default=False,
                help_text="Track user creation, deactivation and role/permission changes.",
            ),
        ),
        # Transaction protection fields
        migrations.AddField(
            model_name="audittrailsetting",
            name="prevent_hard_delete_transactions",
            field=models.BooleanField(
                default=True,
                help_text="If enabled, posted transactions cannot be hard-deleted; only reversed or voided.",
            ),
        ),
        migrations.AddField(
            model_name="audittrailsetting",
            name="require_reason_for_reversal",
            field=models.BooleanField(
                default=True,
                help_text="If enabled, a reason is required when reversing or voiding a transaction.",
            ),
        ),
        # Fraud / high-risk events
        migrations.AddField(
            model_name="audittrailsetting",
            name="track_high_risk_events",
            field=models.BooleanField(
                default=False,
                help_text="Track high-risk events such as backdated postings, overrides and unusual patterns.",
            ),
        ),
        migrations.AddField(
            model_name="audittrailsetting",
            name="escalate_to_audit_risk",
            field=models.BooleanField(
                default=False,
                help_text="Create alerts in the Audit & Risk module when high-risk events are detected.",
            ),
        ),
        # Access control fields
        migrations.AddField(
            model_name="audittrailsetting",
            name="authorized_roles_for_audit_logs",
            field=models.CharField(
                max_length=255,
                blank=True,
                help_text=(
                    "Comma-separated role codes allowed to view full audit logs "
                    "(e.g. system_admin,finance_director,internal_auditor)."
                ),
            ),
        ),
        migrations.AddField(
            model_name="audittrailsetting",
            name="allow_users_see_own_activity",
            field=models.BooleanField(
                default=False,
                help_text="If enabled, non-audit users can see only their own activity log entries.",
            ),
        ),
    ]

