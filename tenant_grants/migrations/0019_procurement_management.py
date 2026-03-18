# Procurement Management: Supplier, Thresholds, PO, Goods Receipt, Supplier Invoice.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("tenant_grants", "0018_purchaserequisitionattachment"),
        ("tenant_users", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Supplier",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=50, unique=True)),
                ("name", models.CharField(max_length=255)),
                ("contact_person", models.CharField(blank=True, max_length=120)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("phone", models.CharField(blank=True, max_length=60)),
                ("address", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="ProcurementThreshold",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount_min", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("amount_max", models.DecimalField(blank=True, decimal_places=2, help_text="Null = no upper limit.", max_digits=14, null=True)),
                ("method", models.CharField(max_length=30, choices=[("direct_purchase", "Direct Purchase"), ("request_quotation", "RFQ"), ("open_tender", "Tender")])),
                ("requires_po_approval", models.BooleanField(default=False)),
                ("po_approval_limit", models.DecimalField(blank=True, decimal_places=2, help_text="POs above this need approval.", max_digits=14, null=True)),
            ],
            options={"ordering": ["amount_min"]},
        ),
        migrations.CreateModel(
            name="PurchaseOrder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("po_number", models.CharField(max_length=50, unique=True)),
                ("procurement_method", models.CharField(blank=True, choices=[("open_tender", "Open Tender"), ("request_quotation", "Request for Quotation"), ("direct_purchase", "Direct Purchase"), ("framework", "Framework Agreement"), ("other", "Other")], default="other", max_length=30)),
                ("order_date", models.DateField()),
                ("expected_delivery_date", models.DateField(blank=True, null=True)),
                ("total_amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("pending_approval", "Pending Approval"), ("approved", "Approved"), ("sent", "Sent to Supplier"), ("partially_received", "Partially Received"), ("received", "Received"), ("closed", "Closed"), ("cancelled", "Cancelled")], default="draft", max_length=30)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("approved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="po_approved", to="tenant_users.tenantuser")),
                ("pr", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="purchase_orders", to="tenant_grants.purchaserequisition")),
                ("supplier", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="purchase_orders", to="tenant_grants.supplier")),
            ],
            options={"ordering": ["-order_date", "-created_at"]},
        ),
        migrations.CreateModel(
            name="PurchaseOrderLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("item_description", models.TextField()),
                ("quantity", models.DecimalField(decimal_places=2, default=1, max_digits=12)),
                ("unit_price", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("received_quantity", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("po", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="tenant_grants.purchaseorder")),
                ("pr_line", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="po_lines", to="tenant_grants.purchaserequisitionline")),
            ],
            options={"ordering": ["po", "id"]},
        ),
        migrations.CreateModel(
            name="GoodsReceipt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("gr_number", models.CharField(max_length=50)),
                ("receipt_date", models.DateField()),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("po", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="goods_receipts", to="tenant_grants.purchaseorder")),
                ("received_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="gr_received", to="tenant_users.tenantuser")),
            ],
            options={"ordering": ["-receipt_date", "-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="goodsreceipt",
            constraint=models.UniqueConstraint(fields=("po", "gr_number"), name="tenant_grants_gr_po_gr_number_uniq"),
        ),
        migrations.CreateModel(
            name="GoodsReceiptLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity_received", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("gr", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="tenant_grants.goodsreceipt")),
                ("po_line", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="gr_lines", to="tenant_grants.purchaseorderline")),
            ],
            options={"ordering": ["gr", "po_line"]},
        ),
        migrations.AddConstraint(
            model_name="goodsreceiptline",
            constraint=models.UniqueConstraint(fields=("gr", "po_line"), name="tenant_grants_grline_gr_po_line_uniq"),
        ),
        migrations.CreateModel(
            name="SupplierInvoice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("invoice_number", models.CharField(max_length=80)),
                ("invoice_date", models.DateField()),
                ("due_date", models.DateField(blank=True, null=True)),
                ("total_amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("pending_approval", "Pending Approval"), ("approved", "Approved"), ("paid", "Paid"), ("cancelled", "Cancelled")], default="draft", max_length=30)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("payment_reference", models.CharField(blank=True, max_length=120)),
                ("payment_date", models.DateField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("approved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="invoice_approved", to="tenant_users.tenantuser")),
                ("po", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="invoices", to="tenant_grants.purchaseorder")),
                ("supplier", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="invoices", to="tenant_grants.supplier")),
            ],
            options={"ordering": ["-invoice_date", "-created_at"]},
        ),
    ]
