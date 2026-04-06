"""
Payment voucher revision rules by workflow status + structured audit logging.

Audit trail uses AuditLog: user_id (edited_by), changed_at (edited_date), old_data/new_data (change_log).

Posted expense payment vouchers: authorized users (`finance:posting.edit_after_post` or
`module:finance.manage`) may apply in-place corrections (same journal id). GL, bank, and grant
budget figures follow from posted `JournalLine` aggregates — no separate reversal journal row.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.dateparse import parse_date

from rbac.models import user_has_permission


def user_can_revise_posted_payment_voucher(request: HttpRequest, tenant_db: str) -> bool:
    """Finance Manager / Admin — `finance:posting.edit_after_post` or `module:finance.manage`."""
    u = getattr(request, "tenant_user", None)
    if not u:
        return False
    if getattr(u, "is_tenant_admin", False):
        return True
    return user_has_permission(u, "finance:posting.edit_after_post", using=tenant_db) or user_has_permission(
        u, "module:finance.manage", using=tenant_db
    )


def _actor_username(request: HttpRequest) -> str:
    u = getattr(request, "tenant_user", None)
    return (getattr(u, "full_name", "") or "").strip() or getattr(u, "email", "") or ""


def snapshot_payment_voucher(entry: Any) -> dict[str, Any]:
    """Serializable header + line summary for diff / audit."""
    from tenant_finance.models import ChartAccount

    lines = list(entry.lines.select_related("account").all())
    exp = next((ln for ln in lines if (ln.debit or Decimal("0")) > 0), None)
    bank = next(
        (
            ln
            for ln in lines
            if (ln.credit or Decimal("0")) > 0
            and ln.account
            and ln.account.type == ChartAccount.Type.ASSET
        ),
        None,
    )
    if not bank:
        bank = next((ln for ln in lines if (ln.credit or Decimal("0")) > 0), None)
    amt = (exp.debit if exp else None) or Decimal("0")
    return {
        "status": entry.status,
        "entry_date": str(entry.entry_date) if entry.entry_date else "",
        "memo": (entry.memo or "")[:255],
        "source_document_no": (entry.source_document_no or "")[:120],
        "project_id": entry.project_id,
        "grant_id": entry.grant_id,
        "payee_name": (entry.payee_name or "")[:255],
        "payee_ref_type": entry.payee_ref_type or "",
        "payee_ref_id": entry.payee_ref_id,
        "payment_method": (entry.payment_method or "")[:40],
        "amount": str(amt.quantize(Decimal("0.01"))),
        "expense_account_id": exp.account_id if exp else None,
        "bank_account_id": bank.account_id if bank else None,
        "budget_line_id": exp.project_budget_line_id if exp else None,
    }


def _material_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    """Any change other than memo / source_document_no (description / reference)."""
    keys = (
        "entry_date",
        "amount",
        "project_id",
        "grant_id",
        "expense_account_id",
        "bank_account_id",
        "budget_line_id",
        "payee_name",
        "payee_ref_type",
        "payee_ref_id",
        "payment_method",
    )
    for k in keys:
        if before.get(k) != after.get(k):
            return True
    return False


def _apply_posted_payment_voucher_minor(
    request: HttpRequest,
    tenant_db: str,
    entry: Any,
    old_snap: dict[str, Any],
    description: str,
    reference_no: str,
    correction_reason: str,
) -> HttpResponse:
    """Posted PV: memo / reference / attachments only; GL lines unchanged."""
    from tenant_finance.models import AuditLog, JournalEntry, JournalEntryAttachment

    try:
        with transaction.atomic(using=tenant_db):
            JournalEntry.objects.using(tenant_db).filter(pk=entry.pk).update(
                memo=description[:255],
                source_document_no=(reference_no or entry.source_document_no or "")[:120],
            )
            for field_name, cat in (
                ("attach_invoice", JournalEntryAttachment.DocumentCategory.INVOICE),
                ("attach_receipt", JournalEntryAttachment.DocumentCategory.RECEIPT),
                ("attach_approval_memo", JournalEntryAttachment.DocumentCategory.APPROVAL_MEMO),
            ):
                fobj = request.FILES.get(field_name)
                if fobj:
                    JournalEntryAttachment.objects.using(tenant_db).create(
                        entry_id=entry.pk,
                        file=fobj,
                        original_filename=getattr(fobj, "name", "") or "",
                        document_category=cat,
                        uploaded_by=request.tenant_user,
                    )
            entry = (
                JournalEntry.objects.using(tenant_db)
                .select_related("project", "grant")
                .prefetch_related("lines__account")
                .get(pk=entry.pk)
            )
            new_after = snapshot_payment_voucher(entry)
            JournalEntryAttachment.sync_for_entry(using=tenant_db, entry=entry)
            AuditLog.objects.using(tenant_db).create(
                model_name="journalentry",
                object_id=entry.id,
                action=AuditLog.Action.UPDATE,
                user_id=getattr(request.tenant_user, "id", None),
                username=_actor_username(request),
                old_data=old_snap,
                new_data={**new_after, "reason_for_change": correction_reason},
                summary=(
                    f"Posted payment voucher {entry.reference} — description/reference/attachment correction. "
                    f"Reason: {correction_reason[:200]}"
                )[:255],
            )
        messages.success(request, f"Payment voucher {entry.reference} updated.")
    except Exception as exc:
        messages.error(request, str(exc))
        return redirect(reverse("tenant_portal:pay_payment_vouchers") + f"?edit={entry.id}")
    return redirect(reverse("tenant_portal:finance_journal_detail", args=[entry.id]))


def _apply_posted_payment_voucher_full(
    request: HttpRequest,
    tenant_db: str,
    entry: Any,
    old_snap: dict[str, Any],
    correction_reason: str,
    entry_date: Any,
    description: str,
    reference_no: str,
    payee: str,
    payee_ref_resolved_type: str,
    payee_ref_resolved_id: Any,
    payment_method: str,
    project_obj: Any,
    grant: Any,
    expense_account: Any,
    payment_account: Any,
    total_amount: Decimal,
) -> HttpResponse:
    """
    Posted PV: replace GL lines in place (same journal id). Updates GL/bank/budget aggregates
    because reporting sums posted JournalLine rows — no reversal journal row.
    """
    from tenant_finance.db_compat import journalentry_has_0040_adjusting_schema
    from tenant_finance.models import AuditLog, JournalEntry, JournalEntryAttachment, JournalLine
    from tenant_finance.services.journal_posting import (
        assert_payment_voucher_ready_to_post,
        assert_sufficient_bank_balance_for_payment_voucher,
    )
    from tenant_finance.services.period_control import assert_can_post_journal
    from tenant_finance.services.transaction_duplicate_detection import assert_no_posted_duplicate

    try:
        assert_can_post_journal(
            using=tenant_db,
            entry_date=entry_date,
            grant=grant,
            user=request.tenant_user,
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect(reverse("tenant_portal:pay_payment_vouchers") + f"?edit={entry.id}")

    je_0040 = journalentry_has_0040_adjusting_schema(tenant_db)

    try:
        with transaction.atomic(using=tenant_db):
            upd: dict[str, Any] = {
                "entry_date": entry_date,
                "memo": description[:255],
                "payee_name": payee[:255],
                "payee_ref_type": payee_ref_resolved_type or "",
                "payee_ref_id": payee_ref_resolved_id,
                "payment_method": payment_method[:40],
                "project_id": project_obj.pk if project_obj else None,
                "grant_id": grant.pk if grant else None,
                "source_document_no": (reference_no or entry.source_document_no or "")[:120],
            }
            if je_0040:
                upd["posting_date"] = entry_date
            JournalEntry.objects.using(tenant_db).filter(pk=entry.pk).update(**upd)

            JournalLine.objects.using(tenant_db).filter(entry_id=entry.pk).delete()
            if not (expense_account and payment_account and total_amount > 0):
                raise ValueError("Expense account, bank account, and positive amount are required.")
            JournalLine.objects.using(tenant_db).create(
                entry_id=entry.pk,
                account=expense_account,
                description=description[:255],
                debit=total_amount,
                credit=Decimal("0"),
                grant=grant,
            )
            JournalLine.objects.using(tenant_db).create(
                entry_id=entry.pk,
                account=payment_account,
                description=description[:255],
                debit=Decimal("0"),
                credit=total_amount,
                grant=grant,
            )

            for field_name, cat in (
                ("attach_invoice", JournalEntryAttachment.DocumentCategory.INVOICE),
                ("attach_receipt", JournalEntryAttachment.DocumentCategory.RECEIPT),
                ("attach_approval_memo", JournalEntryAttachment.DocumentCategory.APPROVAL_MEMO),
            ):
                fobj = request.FILES.get(field_name)
                if fobj:
                    JournalEntryAttachment.objects.using(tenant_db).create(
                        entry_id=entry.pk,
                        file=fobj,
                        original_filename=getattr(fobj, "name", "") or "",
                        document_category=cat,
                        uploaded_by=request.tenant_user,
                    )

            entry = (
                JournalEntry.objects.using(tenant_db)
                .select_related("project", "grant", "currency")
                .prefetch_related("lines__account")
                .get(pk=entry.pk)
            )
            assert_payment_voucher_ready_to_post(using=tenant_db, entry=entry)
            assert_sufficient_bank_balance_for_payment_voucher(using=tenant_db, entry=entry)
            assert_no_posted_duplicate(using=tenant_db, entry=entry, exclude_entry_id=entry.pk)

            JournalEntryAttachment.sync_for_entry(using=tenant_db, entry=entry)

            new_after = snapshot_payment_voucher(entry)
            AuditLog.objects.using(tenant_db).create(
                model_name="journalentry",
                object_id=entry.id,
                action=AuditLog.Action.UPDATE,
                user_id=getattr(request.tenant_user, "id", None),
                username=_actor_username(request),
                old_data=old_snap,
                new_data={**new_after, "reason_for_change": correction_reason},
                summary=(
                    f"Posted payment voucher {entry.reference} — in-place GL correction (no reversal). "
                    f"Reason: {correction_reason[:160]}"
                )[:255],
            )
        messages.success(
            request,
            f"Posted payment voucher {entry.reference} was corrected and balances were updated.",
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect(reverse("tenant_portal:pay_payment_vouchers") + f"?edit={entry.id}")
    except Exception as exc:
        messages.error(request, str(exc))
        return redirect(reverse("tenant_portal:pay_payment_vouchers") + f"?edit={entry.id}")
    return redirect(reverse("tenant_portal:finance_journal_detail", args=[entry.id]))


def apply_payment_voucher_update(request: HttpRequest, tenant_db: str, entry_id: int) -> HttpResponse:
    """
    POST handler for revising an existing payment voucher (expense_payment).
    Expects the same field names as the Payment Entry form, plus entry_id.
    """
    from tenant_finance.models import AuditLog, ChartAccount, JournalEntry, JournalLine, JournalEntryAttachment
    from tenant_grants.models import BudgetLine, Grant, Project
    from tenant_grants.models import Donor as _Donor
    from tenant_users.models import TenantUser as _TenantUser
    from tenant_grants.models import Supplier as _Supplier

    u = request.tenant_user
    can_edit_unposted = user_has_permission(u, "finance:journals.create", using=tenant_db) or user_has_permission(
        u, "module:finance.manage", using=tenant_db
    )
    can_revise_posted = user_can_revise_posted_payment_voucher(request, tenant_db)

    entry = (
        JournalEntry.objects.using(tenant_db)
        .select_related("project", "grant")
        .filter(pk=entry_id)
        .first()
    )
    if not entry:
        messages.error(request, "Payment voucher not found.")
        return redirect(reverse("tenant_portal:pay_payment_vouchers"))

    ref = (entry.reference or "").strip()
    if not ref.upper().startswith("PV-"):
        messages.error(request, "This entry is not a payment voucher.")
        return redirect(reverse("tenant_portal:pay_payment_vouchers"))

    st = (entry.source_type or "").strip()
    jt = (entry.journal_type or "").strip().lower()
    if st != JournalEntry.SourceType.PAYMENT_VOUCHER and jt != "payment_voucher":
        messages.error(request, "This entry is not a payment voucher.")
        return redirect(reverse("tenant_portal:pay_payment_vouchers"))

    if entry.status == JournalEntry.Status.POSTED:
        if not can_revise_posted:
            messages.error(
                request,
                "You do not have permission to correct posted payment vouchers.",
            )
            return redirect(reverse("tenant_portal:finance_journal_detail", args=[entry.id]))
    elif not can_edit_unposted:
        messages.error(request, "You do not have permission to edit payment vouchers.")
        return redirect(reverse("tenant_portal:pay_payment_vouchers"))

    old_snap = snapshot_payment_voucher(entry)

    payment_type = (request.POST.get("payment_type") or "expense_payment").strip()
    if payment_type != "expense_payment":
        messages.error(request, "Editing only supports expense payment vouchers.")
        return redirect(reverse("tenant_portal:pay_payment_vouchers") + f"?edit={entry.id}")

    raw_entry_date = (request.POST.get("entry_date") or "").strip()
    payee_in = (request.POST.get("payee") or "").strip()
    raw_payee_ref = (request.POST.get("payee_ref_type") or "").strip().lower()
    raw_payee_id = (request.POST.get("payee_ref_id") or "").strip()
    payee = payee_in
    payee_ref_resolved_type = ""
    payee_ref_resolved_id = None
    if raw_payee_ref == "supplier" and raw_payee_id.isdigit():
        _s = _Supplier.objects.using(tenant_db).filter(pk=int(raw_payee_id), is_active=True).first()
        if _s:
            payee = (_s.name or "").strip()
            payee_ref_resolved_type = JournalEntry.PayeeReferenceType.SUPPLIER
            payee_ref_resolved_id = _s.pk
        else:
            payee_ref_resolved_type = JournalEntry.PayeeReferenceType.MANUAL
    elif raw_payee_ref == "employee" and raw_payee_id.isdigit():
        _u = _TenantUser.objects.using(tenant_db).filter(pk=int(raw_payee_id), is_active=True).first()
        if _u:
            payee = (_u.get_full_name() or "").strip() or (_u.email or "").strip()
            payee_ref_resolved_type = JournalEntry.PayeeReferenceType.EMPLOYEE
            payee_ref_resolved_id = _u.pk
        else:
            payee_ref_resolved_type = JournalEntry.PayeeReferenceType.MANUAL
    elif raw_payee_ref == "donor" and raw_payee_id.isdigit():
        _d = _Donor.objects.using(tenant_db).filter(pk=int(raw_payee_id), status=_Donor.Status.ACTIVE).first()
        if _d:
            payee = (_d.name or "").strip()
            payee_ref_resolved_type = JournalEntry.PayeeReferenceType.DONOR
            payee_ref_resolved_id = _d.pk
        else:
            payee_ref_resolved_type = JournalEntry.PayeeReferenceType.MANUAL
    elif raw_payee_ref == "manual":
        payee_ref_resolved_type = JournalEntry.PayeeReferenceType.MANUAL
    elif payee:
        payee_ref_resolved_type = JournalEntry.PayeeReferenceType.MANUAL

    payment_method = (request.POST.get("payment_method") or "").strip()
    payment_account_id = request.POST.get("payment_account_id") or ""
    expense_account_id = request.POST.get("expense_account_id") or ""
    grant_id = request.POST.get("grant_id") or None
    project_id = (request.POST.get("project_id") or "").strip()
    budget_line_id = (request.POST.get("budget_code_id") or request.POST.get("budget_line_id") or "").strip()
    description = (request.POST.get("description") or "").strip()
    reference_no = (request.POST.get("reference_no") or "").strip()

    entry_date = parse_date(raw_entry_date) if raw_entry_date else None
    if not entry_date:
        messages.error(request, "Payment date is required.")
        return redirect(reverse("tenant_portal:pay_payment_vouchers") + f"?edit={entry.id}")

    try:
        total_amount = Decimal(str(request.POST.get("amount") or "0").replace(",", ""))
    except Exception:
        total_amount = Decimal("0")

    project_obj = None
    budget_line_obj = None
    if project_id.isdigit():
        project_obj = Project.objects.using(tenant_db).filter(pk=int(project_id)).first()
    if budget_line_id.isdigit():
        budget_line_obj = (
            BudgetLine.objects.using(tenant_db).select_related("grant", "account").filter(pk=int(budget_line_id)).first()
        )
        if budget_line_obj and budget_line_obj.account_id:
            expense_account_id = str(budget_line_obj.account_id)

    grant = Grant.objects.using(tenant_db).filter(pk=int(grant_id)).first() if grant_id and str(grant_id).isdigit() else None

    payment_account = (
        ChartAccount.objects.using(tenant_db).filter(pk=int(payment_account_id)).first() if payment_account_id.isdigit() else None
    )
    expense_account = (
        ChartAccount.objects.using(tenant_db).filter(pk=int(expense_account_id)).first() if expense_account_id.isdigit() else None
    )

    new_snap = {
        "status": entry.status,
        "entry_date": str(entry_date),
        "memo": description[:255],
        "source_document_no": (reference_no or entry.source_document_no or entry.reference or "")[:120],
        "project_id": project_obj.pk if project_obj else None,
        "grant_id": grant.pk if grant else None,
        "payee_name": payee[:255],
        "payee_ref_type": payee_ref_resolved_type or "",
        "payee_ref_id": payee_ref_resolved_id,
        "payment_method": payment_method[:40],
        "amount": str(total_amount.quantize(Decimal("0.01"))),
        "expense_account_id": expense_account.id if expense_account else None,
        "bank_account_id": payment_account.id if payment_account else None,
        "budget_line_id": budget_line_obj.pk if budget_line_obj else None,
    }

    if entry.status == JournalEntry.Status.POSTED:
        correction_reason = (request.POST.get("correction_reason") or "").strip()
        if not correction_reason:
            messages.error(
                request,
                "A reason for the change is required when correcting a posted payment voucher.",
            )
            return redirect(reverse("tenant_portal:pay_payment_vouchers") + f"?edit={entry.id}")
        if not _material_changed(old_snap, new_snap):
            return _apply_posted_payment_voucher_minor(
                request,
                tenant_db,
                entry,
                old_snap,
                description,
                reference_no,
                correction_reason,
            )
        return _apply_posted_payment_voucher_full(
            request,
            tenant_db,
            entry,
            old_snap,
            correction_reason,
            entry_date,
            description,
            reference_no,
            payee,
            payee_ref_resolved_type,
            payee_ref_resolved_id,
            payment_method,
            project_obj,
            grant,
            expense_account,
            payment_account,
            total_amount,
        )

    # Approved + only description / reference / attachments → keep APPROVED, do not touch GL lines
    if entry.status == JournalEntry.Status.APPROVED and not _material_changed(old_snap, new_snap):
        try:
            with transaction.atomic(using=tenant_db):
                entry.memo = description[:255]
                entry.source_document_no = (reference_no or entry.source_document_no or "")[:120]
                entry.save(
                    using=tenant_db,
                    update_fields=["memo", "source_document_no"],
                )
                for field_name, cat in (
                    ("attach_invoice", JournalEntryAttachment.DocumentCategory.INVOICE),
                    ("attach_receipt", JournalEntryAttachment.DocumentCategory.RECEIPT),
                    ("attach_approval_memo", JournalEntryAttachment.DocumentCategory.APPROVAL_MEMO),
                ):
                    fobj = request.FILES.get(field_name)
                    if fobj:
                        JournalEntryAttachment.objects.using(tenant_db).create(
                            entry=entry,
                            file=fobj,
                            original_filename=getattr(fobj, "name", "") or "",
                            document_category=cat,
                            uploaded_by=request.tenant_user,
                        )
                new_after = snapshot_payment_voucher(entry)
                AuditLog.objects.using(tenant_db).create(
                    model_name="journalentry",
                    object_id=entry.id,
                    action=AuditLog.Action.UPDATE,
                    user_id=getattr(request.tenant_user, "id", None),
                    username=_actor_username(request),
                    old_data=old_snap,
                    new_data=new_after,
                    summary=f"Payment voucher {entry.reference} — minor edit (description/reference/attachment)",
                )
            messages.success(request, f"Payment voucher {entry.reference} updated.")
        except Exception as exc:
            messages.error(request, str(exc))
            return redirect(reverse("tenant_portal:pay_payment_vouchers") + f"?edit={entry.id}")
        return redirect(reverse("tenant_portal:finance_journal_detail", args=[entry.id]))

    # Full revision path (draft, pending, approved with material change)
    new_status = JournalEntry.Status.DRAFT
    if entry.status == JournalEntry.Status.DRAFT:
        new_status = JournalEntry.Status.DRAFT
        messages.info(request, "Draft saved.")
    elif entry.status == JournalEntry.Status.INCOMPLETE_DRAFT:
        new_status = JournalEntry.Status.DRAFT
        messages.info(request, "Draft saved.")
    elif entry.status == JournalEntry.Status.PENDING_APPROVAL:
        new_status = JournalEntry.Status.DRAFT
        messages.info(request, "Edits saved as Draft — submit for approval again when ready.")
    elif entry.status == JournalEntry.Status.APPROVED and _material_changed(old_snap, new_snap):
        new_status = JournalEntry.Status.DRAFT
        messages.warning(
            request,
            "Financial details changed — approval was cleared. Submit for approval again when ready.",
        )

    try:
        with transaction.atomic(using=tenant_db):
            entry.refresh_from_db()

            entry.entry_date = entry_date
            entry.memo = description[:255]
            entry.payee_name = payee[:255]
            entry.payee_ref_type = payee_ref_resolved_type or ""
            entry.payee_ref_id = payee_ref_resolved_id
            entry.payment_method = payment_method[:40]
            entry.project = project_obj
            entry.grant = grant
            if reference_no:
                entry.source_document_no = reference_no[:120]
            entry.status = new_status
            entry.submitted_by_id = None
            entry.submitted_at = None
            if new_status == JournalEntry.Status.DRAFT:
                entry.approved_by_id = None
                entry.approved_at = None

            entry.save(
                using=tenant_db,
                update_fields=[
                    "entry_date",
                    "memo",
                    "payee_name",
                    "payee_ref_type",
                    "payee_ref_id",
                    "payment_method",
                    "project",
                    "grant",
                    "source_document_no",
                    "status",
                    "submitted_by_id",
                    "submitted_at",
                    "approved_by_id",
                    "approved_at",
                ],
            )

            JournalLine.objects.using(tenant_db).filter(entry=entry).delete()
            pbl_for_line = None
            if project_obj and budget_line_obj:
                from tenant_grants.models import ProjectBudget, ProjectBudgetLine

                pb = ProjectBudget.objects.using(tenant_db).filter(project=project_obj).first()
                if pb:
                    code = (budget_line_obj.budget_code or "").strip()
                    if code:
                        pbl_for_line = (
                            ProjectBudgetLine.objects.using(tenant_db)
                            .filter(project_budget=pb, category__iexact=code)
                            .first()
                        )
            if expense_account and payment_account and total_amount > 0:
                JournalLine.objects.using(tenant_db).create(
                    entry=entry,
                    account=expense_account,
                    description=description[:255],
                    debit=total_amount,
                    credit=Decimal("0"),
                    grant=grant,
                    project_budget_line=pbl_for_line,
                )
                JournalLine.objects.using(tenant_db).create(
                    entry=entry,
                    account=payment_account,
                    description=description[:255],
                    debit=Decimal("0"),
                    credit=total_amount,
                    grant=grant,
                )

            for field_name, cat in (
                ("attach_invoice", JournalEntryAttachment.DocumentCategory.INVOICE),
                ("attach_receipt", JournalEntryAttachment.DocumentCategory.RECEIPT),
                ("attach_approval_memo", JournalEntryAttachment.DocumentCategory.APPROVAL_MEMO),
            ):
                fobj = request.FILES.get(field_name)
                if fobj:
                    JournalEntryAttachment.objects.using(tenant_db).create(
                        entry=entry,
                        file=fobj,
                        original_filename=getattr(fobj, "name", "") or "",
                        document_category=cat,
                        uploaded_by=request.tenant_user,
                    )

            from tenant_finance.services.payment_voucher_draft_completeness import refresh_payment_voucher_draft_status

            entry.refresh_from_db()
            refresh_payment_voucher_draft_status(using=tenant_db, entry=entry)
            entry.refresh_from_db()

            new_snap_after = snapshot_payment_voucher(entry)
            AuditLog.objects.using(tenant_db).create(
                model_name="journalentry",
                object_id=entry.id,
                action=AuditLog.Action.UPDATE,
                user_id=getattr(request.tenant_user, "id", None),
                username=_actor_username(request),
                old_data=old_snap,
                new_data=new_snap_after,
                summary=f"Payment voucher {entry.reference} revised ({old_snap['status']} → {entry.status})",
            )

        messages.success(request, f"Payment voucher {entry.reference} updated.")
    except Exception as exc:
        messages.error(request, str(exc))
        return redirect(reverse("tenant_portal:pay_payment_vouchers") + f"?edit={entry.id}")

    return redirect(reverse("tenant_portal:finance_journal_detail", args=[entry.id]))


def build_payment_voucher_edit_context(entry: Any) -> dict[str, Any]:
    """Context keys for prefilling the Payment Entry form in edit mode."""
    from tenant_finance.models import ChartAccount

    lines = list(entry.lines.select_related("account").all())
    exp = next((ln for ln in lines if (ln.debit or Decimal("0")) > 0), None)
    bank = next(
        (
            ln
            for ln in lines
            if (ln.credit or Decimal("0")) > 0
            and ln.account
            and ln.account.type == ChartAccount.Type.ASSET
        ),
        None,
    )
    if not bank:
        bank = next((ln for ln in lines if (ln.credit or Decimal("0")) > 0), None)
    amt = exp.debit if exp else Decimal("0")
    ref_doc = (entry.source_document_no or "").strip()
    int_ref = (entry.reference or "").strip()
    ref_for_form = ref_doc if ref_doc and ref_doc != int_ref else ref_doc
    return {
        "id": entry.id,
        "entry_date": entry.entry_date,
        "payee": entry.payee_name or "",
        "payee_ref_type": entry.payee_ref_type or "",
        "payee_ref_id": entry.payee_ref_id or "",
        "payment_method": entry.payment_method or "",
        "payment_account_id": bank.account_id if bank else "",
        "expense_account_id": exp.account_id if exp else "",
        "grant_id": entry.grant_id or "",
        "project_id": entry.project_id or "",
        "budget_code_id": str(exp.project_budget_line_id) if exp and exp.project_budget_line_id else "",
        "amount": amt,
        "description": entry.memo or "",
        "reference_no": ref_for_form,
    }
