# Enforce Grant.project, BudgetLine.project, BudgetLine.account (expense COA) as required.

from django.db import migrations, models
import django.db.models.deletion


def forwards_backfill(apps, schema_editor):
    Grant = apps.get_model("tenant_grants", "Grant")
    Project = apps.get_model("tenant_grants", "Project")
    BudgetLine = apps.get_model("tenant_grants", "BudgetLine")
    ChartAccount = apps.get_model("tenant_finance", "ChartAccount")

    # Grant.project_id: from related budget lines, else first project
    for g in Grant.objects.filter(project__isnull=True).iterator():
        bl = (
            BudgetLine.objects.filter(grant_id=g.pk)
            .exclude(project__isnull=True)
            .order_by("pk")
            .first()
        )
        if bl and bl.project_id:
            Grant.objects.filter(pk=g.pk).update(project_id=bl.project_id)

    first_project = Project.objects.order_by("pk").first()
    if first_project:
        Grant.objects.filter(project__isnull=True).update(project_id=first_project.pk)

    if Grant.objects.filter(project__isnull=True).exists():
        raise RuntimeError(
            "Cannot require Grant.project_id: at least one grant has no project and no Project "
            "row exists to assign. Create a project, link grants, then re-run migrations."
        )

    # BudgetLine.project_id: align with grant.project_id
    for bl in BudgetLine.objects.filter(project__isnull=True).select_related("grant"):
        gid = getattr(bl, "grant_id", None)
        if not gid:
            continue
        g = Grant.objects.filter(pk=gid).values_list("project_id", flat=True).first()
        if g:
            BudgetLine.objects.filter(pk=bl.pk).update(project_id=g)

    if BudgetLine.objects.filter(project__isnull=True).exists():
        raise RuntimeError(
            "Cannot require BudgetLine.project_id: some budget lines could not be linked to a project."
        )

    # BudgetLine.account_id: default to first posting expense account
    exp = (
        ChartAccount.objects.filter(type="EXPENSE", is_active=True, allow_posting=True)
        .order_by("pk")
        .first()
    )
    if exp:
        BudgetLine.objects.filter(account__isnull=True).update(account_id=exp.pk)

    if BudgetLine.objects.filter(account__isnull=True).exists():
        raise RuntimeError(
            "Cannot require BudgetLine.account: add at least one active posting expense account "
            "to the chart, or map all budget lines to an expense account, then re-run migrations."
        )


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_grants", "0041_budgetline_project_posting_status"),
    ]

    operations = [
        migrations.RunPython(forwards_backfill, backwards_noop),
        migrations.AlterField(
            model_name="grant",
            name="project",
            field=models.ForeignKey(
                help_text="Grant must belong to a project for transaction posting.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="grants",
                to="tenant_grants.project",
            ),
        ),
        migrations.AlterField(
            model_name="budgetline",
            name="project",
            field=models.ForeignKey(
                help_text="Implementation project for this line; must match grant.project.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="budget_lines",
                to="tenant_grants.project",
            ),
        ),
        migrations.AlterField(
            model_name="budgetline",
            name="account",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="budget_lines",
                to="tenant_finance.chartaccount",
            ),
        ),
    ]
