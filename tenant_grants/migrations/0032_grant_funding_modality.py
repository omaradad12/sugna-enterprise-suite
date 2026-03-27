from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_grants", "0031_grant_receivable_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="grant",
            name="funding_method",
            field=models.CharField(
                blank=True,
                choices=[
                    ("advance_instalments", "Advance instalments"),
                    ("advance_with_retention", "Advance with retention %"),
                    ("reimbursement", "Reimbursement"),
                    ("mixed", "Mixed"),
                ],
                db_index=True,
                default="",
                help_text="How donor funds are released (instalments, retention, reimbursement, or mixed).",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="grant",
            name="expense_report_approved",
            field=models.BooleanField(
                default=False,
                help_text="For tranches tied to expense report approval: receivable only when True.",
            ),
        ),
        migrations.AddField(
            model_name="grant",
            name="audit_approved",
            field=models.BooleanField(
                default=False,
                help_text="For tranches tied to audit approval: receivable only when True.",
            ),
        ),
        migrations.AddField(
            model_name="grant",
            name="final_report_approved",
            field=models.BooleanField(
                default=False,
                help_text="For retention tranches: receivable only after final report is approved.",
            ),
        ),
        migrations.CreateModel(
            name="GrantTranche",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tranche_no", models.PositiveSmallIntegerField()),
                (
                    "payment_type",
                    models.CharField(
                        choices=[
                            ("advance", "Advance"),
                            ("reimbursement", "Reimbursement"),
                            ("retention", "Retention"),
                        ],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                (
                    "percentage",
                    models.DecimalField(
                        blank=True,
                        decimal_places=4,
                        help_text="Percent of grant ceiling (use when amount is not set).",
                        max_digits=9,
                        null=True,
                    ),
                ),
                (
                    "amount",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Fixed tranche value (use when percentage is not set).",
                        max_digits=14,
                        null=True,
                    ),
                ),
                (
                    "trigger_condition",
                    models.CharField(
                        choices=[
                            ("contract_signing", "Contract signing"),
                            ("expense_report_approval", "Expense report approval"),
                            ("audit_approval", "Audit approval"),
                        ],
                        max_length=40,
                    ),
                ),
                (
                    "due_date",
                    models.DateField(
                        blank=True,
                        help_text="Advance tranches: when due (receivable recognised when due and trigger is met).",
                        null=True,
                    ),
                ),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("notes", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "grant",
                    models.ForeignKey(
                        on_delete=models.CASCADE,
                        related_name="tranches",
                        to="tenant_grants.grant",
                    ),
                ),
            ],
            options={
                "verbose_name": "Grant tranche",
                "verbose_name_plural": "Grant tranches",
                "ordering": ["grant", "sort_order", "tranche_no"],
                "unique_together": {("grant", "tranche_no")},
            },
        ),
    ]
