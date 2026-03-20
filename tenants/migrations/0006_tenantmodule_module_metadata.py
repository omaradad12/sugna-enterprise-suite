# Generated manually: TenantModule through model + Module metadata

from django.db import migrations, models
import django.db.models.deletion


def copy_tenant_modules_m2m_to_through(apps, schema_editor):
    TenantModule = apps.get_model("tenants", "TenantModule")
    connection = schema_editor.connection
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT tenant_id, module_id FROM tenants_tenant_modules")
            rows = cursor.fetchall()
    except Exception:
        return
    for tenant_id, module_id in rows:
        TenantModule.objects.get_or_create(
            tenant_id=tenant_id,
            module_id=module_id,
            defaults={"is_enabled": True},
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0005_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="module",
            name="category",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text="Logical grouping, e.g. core, platform, governance.",
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name="module",
            name="description",
            field=models.TextField(blank=True, help_text="Short description for admins and API consumers."),
        ),
        migrations.AddField(
            model_name="module",
            name="sort_order",
            field=models.PositiveSmallIntegerField(default=0, help_text="Display order in admin and pickers."),
        ),
        migrations.AlterField(
            model_name="module",
            name="code",
            field=models.CharField(db_index=True, max_length=50, unique=True),
        ),
        migrations.AlterModelOptions(
            name="module",
            options={"ordering": ["sort_order", "code"]},
        ),
        migrations.CreateModel(
            name="TenantModule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_enabled", models.BooleanField(db_index=True, default=True)),
                ("enabled_at", models.DateTimeField(auto_now_add=True)),
                ("notes", models.CharField(blank=True, help_text="Internal note (e.g. trial, pilot).", max_length=255)),
                ("limits", models.JSONField(blank=True, default=dict, help_text="Optional JSON limits / feature flags.")),
                (
                    "module",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tenant_modules",
                        to="tenants.module",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tenant_modules",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "ordering": ["module__sort_order", "module__code"],
            },
        ),
        migrations.AddConstraint(
            model_name="tenantmodule",
            constraint=models.UniqueConstraint(fields=("tenant", "module"), name="uniq_tenant_module"),
        ),
        migrations.RunPython(copy_tenant_modules_m2m_to_through, noop_reverse),
        migrations.RemoveField(
            model_name="tenant",
            name="modules",
        ),
        migrations.AddField(
            model_name="tenant",
            name="modules",
            field=models.ManyToManyField(
                blank=True,
                help_text="Enabled modules for this tenant (use TenantModule for metadata).",
                related_name="tenants",
                through="TenantModule",
                to="tenants.module",
            ),
        ),
    ]
