from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_finance", "0009_payment_method_and_register"),
    ]

    operations = [
        migrations.AddField(
            model_name="accountcategory",
            name="status",
            field=models.CharField(
                max_length=20,
                choices=[("active", "Active"), ("inactive", "Inactive")],
                default="active",
                blank=True,
            ),
        ),
    ]

