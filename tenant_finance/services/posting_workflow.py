from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PostingResult:
    entry_id: int
    reference: str
    rule_id: int | None


def _doc_type_for_tx(tx: str) -> str | None:
    m = {
        "payment_voucher": "payment_voucher",
        "receipt_voucher": "receipt_voucher",
        "journal_entry": "journal",
        "bank_transfer": None,
        "staff_advance": None,
        "advance_settlement": None,
    }
    return m.get(tx)


def _posting_rule_tx_type(tx: str) -> str:
    m = {
        "payment_voucher": "payment",
        "receipt_voucher": "receipt",
        "journal_entry": "journal",
        "bank_transfer": "transfer",
    }
    return m.get(tx, "journal")


def post_transaction_to_journal(
    *,
    using: str,
    transaction_type: str,
    entry_date,
    amount: Decimal,
    description: str,
    user,
    grant=None,
    cost_center=None,
    payment_method: str | None = None,
    currency=None,
    donor_id: int | None = None,
    project_id: int | None = None,
    action: str = "post",  # "post" or "save_draft"
) -> PostingResult:
    """
    End-to-end posting workflow:
    - resolves posting rule (priority + JSON conditions) with default mapping fallback
    - validates required dimensions
    - creates JournalEntry + balanced JournalLines
    - generates reference number using DocumentSeries when applicable
    - posts (or saves draft) within an atomic transaction
    - writes audit records
    """
    from django.db import transaction
    from django.core.exceptions import ValidationError

    from tenant_finance.models import AuditLog, ChartAccount, JournalEntry, JournalLine, ProjectDimensionMapping
    from tenant_finance.services.numbering import generate_document_number
    from tenant_finance.services.posting_engine import resolve_posting

    tx_type = _posting_rule_tx_type(transaction_type)
    if amount is None:
        amount = Decimal("0")
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")

    # Resolve dimension context
    project = None
    if grant is not None and getattr(grant, "project_id", None):
        project = grant.project
    if project_id and not project:
        project = None
        try:
            # project_id can be used when posting without grant
            from tenant_grants.models import Project

            project = Project.objects.using(using).filter(pk=project_id).first()
        except Exception:
            project = None

    mapping = None
    if project is not None:
        mapping = (
            ProjectDimensionMapping.objects.using(using)
            .filter(project=project)
            .first()
        )

    # Rule resolution
    resolution = resolve_posting(
        using=using,
        transaction_type=tx_type,
        amount=amount,
        project_id=project.id if project else None,
        grant_id=getattr(grant, "id", None),
        donor_id=donor_id or getattr(getattr(grant, "donor", None), "id", None),
        cost_center_id=getattr(cost_center, "id", None) if cost_center else None,
        payment_method=payment_method,
        currency=getattr(currency, "code", None) if currency else None,
    )

    # Required dimension validation (rule-driven)
    apply_dim = (resolution.apply_dimension or "none").strip().lower()
    if apply_dim == "grant" and not grant:
        raise ValueError("Grant is required for this posting rule.")
    if apply_dim == "project" and not project:
        raise ValueError("Project is required for this posting rule.")
    if apply_dim == "cost_center" and not cost_center and not (mapping and mapping.cost_center_id):
        raise ValueError("Cost center is required for this posting rule.")

    debit_account = ChartAccount.objects.using(using).get(pk=resolution.debit_account_id)
    credit_account = ChartAccount.objects.using(using).get(pk=resolution.credit_account_id)
    if debit_account.id == credit_account.id:
        raise ValueError("Debit and credit accounts cannot be the same.")

    status = JournalEntry.Status.DRAFT if action == "save_draft" else JournalEntry.Status.POSTED

    with transaction.atomic(using=using):
        entry = JournalEntry.objects.using(using).create(
            entry_date=entry_date,
            memo=(description or "").strip(),
            grant=grant,
            cost_center=cost_center or (mapping.cost_center if mapping else None),
            currency=currency,
            status=JournalEntry.Status.DRAFT,  # create draft first; POSTED transition enforces controls
            created_by=user,
            payment_method=(payment_method or "").strip(),
        )

        # Numbering (enterprise series) when applicable
        doc_type = _doc_type_for_tx(transaction_type)
        if doc_type:
            gen = generate_document_number(
                using=using,
                document_type=doc_type,
                entry_date=entry_date,
                project=project,
                grant=grant,
            )
            entry.reference = gen.value
            entry.save(update_fields=["reference"])

        # Create balanced lines
        JournalLine.objects.using(using).create(
            entry=entry,
            account=debit_account,
            description=(description or "").strip(),
            debit=amount,
            credit=Decimal("0"),
        )
        JournalLine.objects.using(using).create(
            entry=entry,
            account=credit_account,
            description=(description or "").strip(),
            debit=Decimal("0"),
            credit=amount,
        )

        if status == JournalEntry.Status.POSTED:
            entry.status = JournalEntry.Status.POSTED
            try:
                entry.save(using=using, update_fields=["status"])
            except ValidationError as exc:
                # Preserve useful error messages for UI
                msg = "; ".join(sum(exc.message_dict.values(), [])) if hasattr(exc, "message_dict") else str(exc)
                raise ValueError(msg)

        AuditLog.objects.using(using).create(
            model_name="posting",
            object_id=entry.id,
            action=AuditLog.Action.CREATE,
            user_id=getattr(user, "id", None),
            username=(getattr(user, "full_name", "") or getattr(user, "email", "") or ""),
            summary=f"Posted {transaction_type} to journal {entry.reference or entry.id}.",
            new_data={
                "transaction_type": transaction_type,
                "journal_entry_id": entry.id,
                "reference": entry.reference,
                "rule_id": resolution.rule_id,
                "debit_account_id": debit_account.id,
                "credit_account_id": credit_account.id,
                "amount": str(amount),
                "grant_id": getattr(grant, "id", None),
                "project_id": getattr(project, "id", None) if project else None,
                "cost_center_id": getattr(entry.cost_center, "id", None),
                "currency_id": getattr(currency, "id", None),
                "payment_method": (payment_method or "").strip(),
                "status": entry.status,
            },
        )

    return PostingResult(entry_id=entry.id, reference=entry.reference or "", rule_id=resolution.rule_id)

