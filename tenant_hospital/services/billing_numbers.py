from __future__ import annotations

from tenant_hospital.services.order_numbers import next_prefixed_number


def next_invoice_number(using: str) -> str:
    from tenant_hospital.models import PatientInvoice

    return next_prefixed_number(using, model=PatientInvoice, field="invoice_number", prefix="INV-", width=6)
