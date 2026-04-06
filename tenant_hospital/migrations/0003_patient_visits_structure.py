# Generated manually for patient master + OPD/IPD/ER visit structure

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_hospital", "0002_insuranceplan_clinicalnote_laborder_laborderline_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="patient",
            old_name="sex",
            new_name="gender",
        ),
        migrations.AddField(
            model_name="patient",
            name="allergies",
            field=models.TextField(blank=True, help_text="Known allergies and adverse reactions."),
        ),
        migrations.AlterField(
            model_name="patient",
            name="emergency_contact_name",
            field=models.CharField(
                blank=True,
                help_text="Next of kin or emergency contact name.",
                max_length=160,
            ),
        ),
        migrations.CreateModel(
            name="PatientDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("file", models.FileField(max_length=255, upload_to="hospital/patient_docs/%Y/%m/")),
                ("notes", models.CharField(blank=True, max_length=255)),
                ("uploaded_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "patient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="documents",
                        to="tenant_hospital.patient",
                    ),
                ),
            ],
            options={
                "ordering": ["-uploaded_at", "id"],
            },
        ),
        migrations.AddField(
            model_name="encounter",
            name="visit_kind",
            field=models.CharField(
                choices=[
                    ("opd", "Outpatient (OPD)"),
                    ("ipd", "Inpatient (IPD)"),
                    ("emergency", "Emergency"),
                    ("unspecified", "Unspecified"),
                ],
                db_index=True,
                default="unspecified",
                help_text="Set by workflow: OPD, IPD, or emergency—not stored on Patient.",
                max_length=20,
            ),
        ),
        migrations.AddIndex(
            model_name="encounter",
            index=models.Index(fields=["visit_kind", "started_at"], name="tenant_hosp_visit_k_0a1b2c_idx"),
        ),
        migrations.CreateModel(
            name="EmergencyVisit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "triage_level",
                    models.CharField(
                        blank=True,
                        help_text="e.g. ESI level or local triage code.",
                        max_length=40,
                    ),
                ),
                ("emergency_notes", models.TextField(blank=True)),
                (
                    "outcome",
                    models.CharField(
                        choices=[
                            ("discharge", "Discharge"),
                            ("admit", "Admit"),
                            ("refer", "Refer"),
                        ],
                        db_index=True,
                        default="discharge",
                        max_length=20,
                    ),
                ),
                (
                    "encounter",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="emergency_detail",
                        to="tenant_hospital.encounter",
                    ),
                ),
            ],
            options={
                "ordering": ["-id"],
            },
        ),
        migrations.CreateModel(
            name="OutpatientVisit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("visit_date", models.DateField(db_index=True)),
                ("symptoms", models.TextField(blank=True)),
                ("diagnosis", models.TextField(blank=True)),
                ("prescription", models.TextField(blank=True)),
                ("follow_up_date", models.DateField(blank=True, null=True)),
                (
                    "department",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="opd_visits",
                        to="tenant_hospital.department",
                    ),
                ),
                (
                    "doctor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="opd_visits",
                        to="tenant_hospital.provider",
                    ),
                ),
                (
                    "encounter",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="opd_detail",
                        to="tenant_hospital.encounter",
                    ),
                ),
            ],
            options={
                "ordering": ["-visit_date", "id"],
            },
        ),
        migrations.AddField(
            model_name="admission",
            name="admission_diagnosis",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="admission",
            name="discharge_summary",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="admission",
            name="attending_provider",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="admissions_attending",
                to="tenant_hospital.provider",
            ),
        ),
        migrations.AddField(
            model_name="admission",
            name="encounter",
            field=models.OneToOneField(
                blank=True,
                help_text="IPD encounter for this admission (created at admit time).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="admission",
                to="tenant_hospital.encounter",
            ),
        ),
    ]
