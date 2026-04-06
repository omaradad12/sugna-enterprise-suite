from __future__ import annotations

from django.db import transaction


def next_mrn(using: str, prefix: str = "MRN") -> str:
    """
    Allocate a new MRN in the tenant DB.

    Uses a simple increment based on Patient.id to avoid extra counter tables.
    Format: {prefix}-{number:06d}
    """
    from tenant_hospital.models import Patient

    with transaction.atomic(using=using):
        last = (
            Patient.objects.using(using)
            .order_by("-id")
            .values_list("id", flat=True)
            .first()
        ) or 0
        return f"{prefix}-{(last + 1):06d}"

