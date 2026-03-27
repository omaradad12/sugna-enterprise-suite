"""Persist and validate FundingSource mixed-modality payment structure lines."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tenant_grants.models import FundingSource


def replace_funding_source_payment_structure_from_post(
    request: HttpRequest,
    funding_source: FundingSource,
    using: str,
) -> None:
    """Replace payment structure rows from POST (ps_* field lists)."""
    from tenant_grants.models import FundingSourcePaymentStructure

    source_id_raw = (request.POST.get("source_id") or "").strip()
    action = (request.POST.get("action") or "").strip().lower()
    if action == "edit":
        if not source_id_raw.isdigit():
            raise ValidationError("Invalid funding modality selected for structure update.")
        if int(source_id_raw) != int(funding_source.pk):
            raise ValidationError(
                "Payment structure mismatch detected. Please reopen the modality and try again."
            )

    FundingSourcePaymentStructure.objects.using(using).filter(funding_source_id=funding_source.pk).delete()

    types = request.POST.getlist("ps_component_type")
    pcts = request.POST.getlist("ps_percentage")
    trigs = request.POST.getlist("ps_payment_trigger")
    sorts = request.POST.getlist("ps_sort_order")

    valid_ct = {c[0] for c in FundingSourcePaymentStructure.ComponentType.choices}
    valid_tr = {c[0] for c in FundingSourcePaymentStructure.PaymentTrigger.choices}

    to_create: list[FundingSourcePaymentStructure] = []
    for i in range(len(types)):
        ct = (types[i] if i < len(types) else "").strip()
        if not ct or ct not in valid_ct:
            continue
        pct_s = (pcts[i] if i < len(pcts) else "").strip()
        try:
            pct = Decimal(pct_s.replace(",", "")) if pct_s else Decimal("0")
        except (InvalidOperation, ValueError):
            continue
        if pct <= 0:
            continue
        tr = (trigs[i] if i < len(trigs) else "").strip()
        if tr not in valid_tr:
            continue
        so_s = (sorts[i] if i < len(sorts) else "").strip()
        sort_order = int(so_s) if so_s.isdigit() else i
        to_create.append(
            FundingSourcePaymentStructure(
                funding_source_id=funding_source.pk,
                sort_order=sort_order,
                component_type=ct,
                percentage=pct,
                payment_trigger=tr,
            )
        )

    for obj in to_create:
        obj.full_clean()
        obj.save(using=using)


def replace_funding_source_component_account_maps_from_post(
    request: HttpRequest,
    funding_source: FundingSource,
    using: str,
) -> None:
    """
    Replace component-account mapping rows from POST (acc_* field lists).
    """
    from tenant_finance.models import BankAccount, ChartAccount
    from tenant_grants.models import FundingSourceComponentAccountMap, FundingSourcePaymentStructure

    FundingSourceComponentAccountMap.objects.using(using).filter(funding_source_id=funding_source.pk).delete()

    components = request.POST.getlist("acc_component_type")
    recv_ids = request.POST.getlist("acc_receivable_account_id")
    inc_ids = request.POST.getlist("acc_income_account_id")
    deferred_ids = request.POST.getlist("acc_deferred_income_account_id")
    retention_ids = request.POST.getlist("acc_retention_account_id")
    bank_types = request.POST.getlist("acc_bank_account_type")

    valid_components = {c[0] for c in FundingSourcePaymentStructure.ComponentType.choices}
    valid_bank_types = {c[0] for c in BankAccount.AccountType.choices}

    for i in range(len(components)):
        comp = (components[i] if i < len(components) else "").strip()
        if not comp or comp not in valid_components:
            continue
        recv_id = (recv_ids[i] if i < len(recv_ids) else "").strip()
        inc_id = (inc_ids[i] if i < len(inc_ids) else "").strip()
        deferred_id = (deferred_ids[i] if i < len(deferred_ids) else "").strip()
        retention_id = (retention_ids[i] if i < len(retention_ids) else "").strip()
        bank_t = (bank_types[i] if i < len(bank_types) else "").strip()
        if bank_t and bank_t not in valid_bank_types:
            bank_t = ""

        recv = ChartAccount.objects.using(using).filter(pk=int(recv_id)).first() if recv_id.isdigit() else None
        inc = ChartAccount.objects.using(using).filter(pk=int(inc_id)).first() if inc_id.isdigit() else None
        deferred_acc = (
            ChartAccount.objects.using(using).filter(pk=int(deferred_id)).first() if deferred_id.isdigit() else None
        )
        retention_acc = (
            ChartAccount.objects.using(using).filter(pk=int(retention_id)).first() if retention_id.isdigit() else None
        )
        if recv is None and inc is None and deferred_acc is None and retention_acc is None and not bank_t:
            continue

        obj = FundingSourceComponentAccountMap(
            funding_source_id=funding_source.pk,
            component_type=comp,
            receivable_account=recv,
            income_account=inc,
            deferred_income_account=deferred_acc,
            retention_account=retention_acc,
            bank_account_type=bank_t,
        )
        obj.full_clean()
        obj.save(using=using)
