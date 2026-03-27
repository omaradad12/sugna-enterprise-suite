"""Persist grant tranche lines from HTTP POST (Project / Grant dimensions form)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from django.utils.dateparse import parse_date

if TYPE_CHECKING:
    from django.http import HttpRequest

    from tenant_grants.models import Grant


def sync_grant_tranches_from_funding_structure(grant: Grant, using: str | None = None) -> None:
    """
    For grants linked to a Mixed modality funding source, replace tranche lines from
    the catalog payment structure (percentages → receivable schedule).
    """
    from tenant_grants.models import FundingSource, FundingSourcePaymentStructure, GrantTranche

    if not grant.funding_modality_id or not grant.pk:
        return
    fs = (
        FundingSource.objects.using(using)
        .filter(pk=grant.funding_modality_id)
        .prefetch_related("payment_structure")
        .first()
    )
    if not fs or fs.modality_type != FundingSource.ModalityType.MIXED_MODALITY:
        return
    lines = list(fs.payment_structure.all().order_by("sort_order", "id"))
    if not lines:
        return

    ct_map = {
        FundingSourcePaymentStructure.ComponentType.ADVANCE: GrantTranche.PaymentType.ADVANCE,
        FundingSourcePaymentStructure.ComponentType.REIMBURSEMENT: GrantTranche.PaymentType.REIMBURSEMENT,
        FundingSourcePaymentStructure.ComponentType.RETENTION: GrantTranche.PaymentType.RETENTION,
        FundingSourcePaymentStructure.ComponentType.INSTALMENT: GrantTranche.PaymentType.INSTALMENT,
        FundingSourcePaymentStructure.ComponentType.MILESTONE_BASED: GrantTranche.PaymentType.MILESTONE_BASED,
    }
    trig_map = {
        FundingSourcePaymentStructure.PaymentTrigger.AGREEMENT_SIGNED: GrantTranche.TriggerCondition.CONTRACT_SIGNING,
        FundingSourcePaymentStructure.PaymentTrigger.EXPENSE_REPORT_APPROVED: GrantTranche.TriggerCondition.EXPENSE_REPORT_APPROVAL,
        FundingSourcePaymentStructure.PaymentTrigger.MILESTONE_COMPLETED: GrantTranche.TriggerCondition.MILESTONE_COMPLETED,
        FundingSourcePaymentStructure.PaymentTrigger.FINAL_AUDIT_APPROVED: GrantTranche.TriggerCondition.AUDIT_APPROVAL,
    }

    GrantTranche.objects.using(using).filter(grant_id=grant.pk).delete()
    for i, ln in enumerate(lines, start=1):
        pt = ct_map.get(ln.component_type, GrantTranche.PaymentType.ADVANCE)
        trig = trig_map.get(ln.payment_trigger, GrantTranche.TriggerCondition.CONTRACT_SIGNING)
        obj = GrantTranche(
            grant=grant,
            tranche_no=i,
            payment_type=pt,
            percentage=ln.percentage,
            amount=None,
            trigger_condition=trig,
            due_date=None,
            sort_order=ln.sort_order,
        )
        obj.full_clean()
        obj.save(using=using)


def replace_grant_tranches_from_post(request: HttpRequest, grant: Grant, using: str) -> None:
    from tenant_grants.models import FundingSource, GrantTranche

    if grant.funding_modality_id:
        mt = (
            FundingSource.objects.using(using)
            .filter(pk=grant.funding_modality_id)
            .values_list("modality_type", flat=True)
            .first()
        )
        if mt == FundingSource.ModalityType.MIXED_MODALITY:
            return

    GrantTranche.objects.using(using).filter(grant_id=grant.pk).delete()

    nos = request.POST.getlist("tranche_no")
    if not nos:
        return

    pay_types = request.POST.getlist("tranche_payment_type")
    triggers = request.POST.getlist("tranche_trigger")
    pcts = request.POST.getlist("tranche_percentage")
    amts = request.POST.getlist("tranche_amount")
    dues = request.POST.getlist("tranche_due_date")
    sorts = request.POST.getlist("tranche_sort_order")

    valid_pt = {c[0] for c in GrantTranche.PaymentType.choices}
    valid_tr = {c[0] for c in GrantTranche.TriggerCondition.choices}

    to_create: list[GrantTranche] = []
    for i, raw_no in enumerate(nos):
        raw_no = (raw_no or "").strip()
        if not raw_no:
            continue
        try:
            tr_no = int(raw_no)
        except ValueError:
            continue

        pt = (pay_types[i] if i < len(pay_types) else "") or GrantTranche.PaymentType.ADVANCE
        if pt not in valid_pt:
            pt = GrantTranche.PaymentType.ADVANCE
        trig = (triggers[i] if i < len(triggers) else "") or GrantTranche.TriggerCondition.CONTRACT_SIGNING
        if trig not in valid_tr:
            trig = GrantTranche.TriggerCondition.CONTRACT_SIGNING

        pct_s = (pcts[i] if i < len(pcts) else "").strip()
        amt_s = (amts[i] if i < len(amts) else "").strip()
        pct = None
        amt = None
        if pct_s:
            try:
                pct = Decimal(pct_s.replace(",", ""))
            except (InvalidOperation, ValueError):
                pct = None
        if amt_s:
            try:
                amt = Decimal(amt_s.replace(",", ""))
            except (InvalidOperation, ValueError):
                amt = None
        if (pct is None or pct <= 0) and (amt is None or amt <= 0):
            continue

        due_s = (dues[i] if i < len(dues) else "").strip()
        due = parse_date(due_s) if due_s else None
        so_s = (sorts[i] if i < len(sorts) else "").strip()
        sort_order = int(so_s) if so_s.isdigit() else i

        to_create.append(
            GrantTranche(
                grant=grant,
                tranche_no=tr_no,
                payment_type=pt,
                percentage=pct if pct and pct > 0 else None,
                amount=amt if amt and amt > 0 else None,
                trigger_condition=trig,
                due_date=due,
                sort_order=sort_order,
            )
        )

    for obj in to_create:
        obj.full_clean()
        obj.save(using=using)
