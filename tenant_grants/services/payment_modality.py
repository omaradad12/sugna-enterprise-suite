"""
Payment modality (FundingSource) integration for grants and receivable logic.

Maps catalog modalities to Grant.funding_method, exposes flags for validation and
downstream receivable / retention / reimbursement behaviour.
"""

from __future__ import annotations

from django.db import connections

from tenant_grants.models import FundingSource, Grant


def ensure_component_account_map_schema(using: str) -> None:
    """
    Backward-compatible schema guard for tenants missing late-added nullable columns.
    """
    from tenant_grants.models import FundingSourceComponentAccountMap

    table = FundingSourceComponentAccountMap._meta.db_table
    with connections[using].cursor() as cursor:
        cursor.execute(
            f"""
            ALTER TABLE {table}
            ADD COLUMN IF NOT EXISTS deferred_income_account_id bigint NULL,
            ADD COLUMN IF NOT EXISTS retention_account_id bigint NULL;
            """
        )


def modality_type_to_grant_funding_method(modality_type: str) -> str:
    """Map FundingSource.ModalityType value to Grant.FundingMethod code."""
    m = FundingSource.ModalityType
    g = Grant.FundingMethod
    mapping = {
        m.ADVANCE: g.ADVANCE_INSTALMENTS,
        m.INSTALMENT: g.ADVANCE_INSTALMENTS,
        m.REIMBURSEMENT: g.REIMBURSEMENT,
        m.ADVANCE_WITH_RETENTION: g.ADVANCE_WITH_RETENTION,
        m.MILESTONE_BASED: g.MIXED,
        m.COST_SHARE: g.MIXED,
        m.MIXED_MODALITY: g.MIXED,
    }
    return mapping.get(modality_type, "")


def sync_grant_from_funding_modality(grant: Grant) -> None:
    """
    When a grant links to a FundingSource modality, align legacy funding_method
    so tranche validation and receivable rules stay consistent.
    """
    if not grant.funding_modality_id:
        return
    fs = getattr(grant, "funding_modality", None)
    if fs is None:
        return
    fm = modality_type_to_grant_funding_method(fs.modality_type)
    if fm:
        grant.funding_method = fm


def modality_expects_retention_balance(fs: FundingSource) -> bool:
    return fs.modality_type in (
        FundingSource.ModalityType.ADVANCE_WITH_RETENTION,
        FundingSource.ModalityType.MIXED_MODALITY,
    )


def modality_controls_reimbursement_claims(fs: FundingSource) -> bool:
    return fs.modality_type in (
        FundingSource.ModalityType.REIMBURSEMENT,
        FundingSource.ModalityType.MIXED_MODALITY,
        FundingSource.ModalityType.COST_SHARE,
    )


def modality_requires_reporting_gate(fs: FundingSource) -> bool:
    return bool(fs.requires_reporting_before_next_payment)


def tranche_payment_type_to_component_type(payment_type: str) -> str:
    from tenant_grants.models import FundingSourcePaymentStructure, GrantTranche

    if payment_type == GrantTranche.PaymentType.ADVANCE:
        return FundingSourcePaymentStructure.ComponentType.ADVANCE
    if payment_type == GrantTranche.PaymentType.REIMBURSEMENT:
        return FundingSourcePaymentStructure.ComponentType.REIMBURSEMENT
    if payment_type == GrantTranche.PaymentType.RETENTION:
        return FundingSourcePaymentStructure.ComponentType.RETENTION
    if payment_type == GrantTranche.PaymentType.INSTALMENT:
        return FundingSourcePaymentStructure.ComponentType.INSTALMENT
    if payment_type == GrantTranche.PaymentType.MILESTONE_BASED:
        return FundingSourcePaymentStructure.ComponentType.MILESTONE_BASED
    return FundingSourcePaymentStructure.ComponentType.ADVANCE


def resolve_component_account_mapping(
    *,
    using: str,
    grant: Grant | None,
    component_type: str = "",
) -> dict:
    """
    Resolve mapped GL accounts and preferred bank account type from
    Grant.funding_modality template.
    """
    from tenant_grants.models import FundingSourceComponentAccountMap, FundingSourcePaymentStructure

    ensure_component_account_map_schema(using)

    if not grant or not grant.funding_modality_id:
        return {}
    ct = (component_type or "").strip()
    if not ct:
        ct = FundingSourcePaymentStructure.ComponentType.ADVANCE
    row = (
        FundingSourceComponentAccountMap.objects.using(using)
        .select_related(
            "receivable_account",
            "income_account",
            "deferred_income_account",
            "retention_account",
        )
        .filter(funding_source_id=grant.funding_modality_id, component_type=ct)
        .first()
    )
    if not row:
        return {}
    return {
        "component_type": ct,
        "receivable_account": row.receivable_account,
        "income_account": row.income_account,
        "deferred_income_account": row.deferred_income_account,
        "retention_account": row.retention_account,
        "bank_account_type": (row.bank_account_type or "").strip(),
    }


def has_complete_gl_mapping(
    *,
    using: str,
    grant: Grant | None = None,
    funding_source: FundingSource | None = None,
    component_type: str = "",
) -> bool:
    """
    True when modality mapping has all required GL accounts.

    Required mapping keys:
    - receivable_account
    - income_account
    - deferred_income_account
    - retention_account
    """
    required_keys = (
        "receivable_account",
        "income_account",
        "deferred_income_account",
        "retention_account",
    )
    ensure_component_account_map_schema(using)
    if grant is None and funding_source is not None and not (component_type or "").strip():
        from tenant_grants.models import FundingSourceComponentAccountMap

        rows = list(
            FundingSourceComponentAccountMap.objects.using(using)
            .filter(funding_source_id=funding_source.pk)
            .only(
                "receivable_account_id",
                "income_account_id",
                "deferred_income_account_id",
                "retention_account_id",
            )
        )
        if not rows:
            return False
        return all(
            bool(r.receivable_account_id and r.income_account_id and r.deferred_income_account_id and r.retention_account_id)
            for r in rows
        )

    from tenant_grants.models import Grant as GrantModel

    target_grant = grant
    if target_grant is None and funding_source is not None:
        # Minimal grant-like object so resolve_component_account_mapping can reuse one path.
        target_grant = GrantModel(funding_modality=funding_source)
    mapping = resolve_component_account_mapping(
        using=using,
        grant=target_grant,
        component_type=component_type,
    )
    if not mapping:
        return False
    return all(mapping.get(k) is not None for k in required_keys)
