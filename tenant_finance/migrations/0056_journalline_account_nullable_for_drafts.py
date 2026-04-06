# Generated manually for draft Excel import (incomplete lines until posted).

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0055_chartaccount_allow_posting"),
    ]

    operations = [
        migrations.AlterField(
            model_name="journalline",
            name="account",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="tenant_finance.chartaccount",
            ),
        ),
    ]
