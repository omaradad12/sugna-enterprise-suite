from __future__ import annotations

from django.db import transaction


def next_prefixed_number(using: str, *, model, field: str, prefix: str, width: int = 6) -> str:
    """Allocate LO-000001 style numbers by scanning existing values with the same prefix."""
    with transaction.atomic(using=using):
        last = (
            model.objects.using(using)
            .filter(**{f"{field}__startswith": prefix})
            .order_by("-id")
            .values_list(field, flat=True)
            .first()
        )
        n = 1
        if last and isinstance(last, str) and last.startswith(prefix):
            tail = last[len(prefix) :].strip()
            if tail.isdigit():
                n = int(tail) + 1
        return f"{prefix}{n:0{width}d}"


def next_lab_order_number(using: str) -> str:
    from tenant_hospital.models import LabOrder

    return next_prefixed_number(using, model=LabOrder, field="order_number", prefix="LO-", width=6)


def next_pharmacy_order_number(using: str) -> str:
    from tenant_hospital.models import PharmacyOrder

    return next_prefixed_number(using, model=PharmacyOrder, field="order_number", prefix="PH-", width=6)
