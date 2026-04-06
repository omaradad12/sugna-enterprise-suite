# Generated manually for payment voucher dependency logic

from collections import defaultdict

from django.db import migrations, models
import django.db.models.deletion


def forwards_backfill_project_and_headings(apps, schema_editor):
    BudgetLine = apps.get_model("tenant_grants", "BudgetLine")
    Grant = apps.get_model("tenant_grants", "Grant")
    db = schema_editor.connection.alias

    by_grant = defaultdict(list)
    for bl in BudgetLine.objects.using(db).all().iterator():
        by_grant[bl.grant_id].append(bl)

    for gid, lines in by_grant.items():
        if not gid:
            continue
        codes = [(getattr(bl, "budget_line_code", None) or "").strip() for bl in lines]
        s = {c for c in codes if c}
        parents = set()
        for c in s:
            for o in s:
                if o != c and o.startswith(c + "."):
                    parents.add(c)
                    break
        pid = Grant.objects.using(db).filter(pk=gid).values_list("project_id", flat=True).first()
        for bl in lines:
            code = (getattr(bl, "budget_line_code", None) or "").strip()
            updates = {}
            if pid and not getattr(bl, "project_id", None):
                updates["project_id"] = pid
            if code in parents:
                updates["is_heading"] = True
            if updates:
                BudgetLine.objects.using(db).filter(pk=bl.pk).update(**updates)


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_grants", "0040_budgetline_category_blank"),
    ]

    operations = [
        migrations.AddField(
            model_name="budgetline",
            name="project",
            field=models.ForeignKey(
                blank=True,
                help_text="Implementation project for this line; should match grant.project when the grant is project-scoped.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="budget_lines",
                to="tenant_grants.project",
            ),
        ),
        migrations.AddField(
            model_name="budgetline",
            name="is_posting",
            field=models.BooleanField(
                db_index=True,
                default=True,
                help_text="False for section headings or non-posting summary rows.",
            ),
        ),
        migrations.AddField(
            model_name="budgetline",
            name="status",
            field=models.CharField(
                choices=[("active", "Active"), ("inactive", "Inactive")],
                db_index=True,
                default="active",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="budgetline",
            name="is_heading",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="True for hierarchy headings that must not be selected for transactions.",
            ),
        ),
        migrations.RunPython(forwards_backfill_project_and_headings, backwards_noop),
    ]
