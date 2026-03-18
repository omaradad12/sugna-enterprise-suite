from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0027_postingrule_conditions_and_priority"),
        ("tenant_users", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="BudgetOverrideRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected"), ("cancelled", "Cancelled")], db_index=True, default="pending", max_length=20)),
                ("requested_at", models.DateTimeField(auto_now_add=True)),
                ("reason", models.TextField(blank=True)),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                ("decision_note", models.TextField(blank=True)),
                ("check_snapshot", models.JSONField(blank=True, default=dict)),
                ("decided_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="tenant_users.tenantuser")),
                ("entry", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="budget_override_requests", to="tenant_finance.journalentry")),
                ("requested_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="tenant_users.tenantuser")),
                ("rule", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="tenant_finance.budgetcontrolrule")),
            ],
            options={
                "ordering": ["-requested_at"],
            },
        ),
        migrations.AddIndex(
            model_name="budgetoverriderequest",
            index=models.Index(fields=["entry", "status"], name="tenant_fina_entry_id_ef5d0c_idx"),
        ),
    ]

