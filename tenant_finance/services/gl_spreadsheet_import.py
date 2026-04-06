"""
Import General Ledger–style spreadsheet rows as posted journal entries (Dr expense, Cr bank).

Expects columns similar to export layout: Date, Grant, Donor, Budgetcode, Budget line,
Description, Debit, Credit, Currency, Document reference; Account columns may be empty.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from tenant_finance.models import ChartAccount, Currency, JournalEntry, JournalLine
from tenant_finance.services.journal_posting import assert_balanced_line_amounts
from tenant_grants.models import Grant, Project, ProjectBudgetLine


@dataclass
class ImportRowResult:
    row_index: int
    document_reference: str
    status: str  # "posted" | "skipped" | "error"
    message: str = ""
    entry_id: int | None = None


def _norm_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).strip().lower())


def normalize_dataframe_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map flexible header names to canonical keys."""
    alias_map = {
        "date": "date",
        "journalref": "journal_ref",
        "accountcode": "account_code",
        "accountname": "account_name",
        "grant": "grant",
        "donor": "donor",
        "budgetcode": "budgetcode",
        "budgetline": "budget_line",
        "description": "description",
        "debit": "debit",
        "credit": "credit",
        "runningbalance": "running_balance",
        "currency": "currency",
        "documentreference": "document_reference",
    }
    rename: dict[str, str] = {}
    for c in df.columns:
        k = _norm_key(c)
        if k in alias_map:
            rename[c] = alias_map[k]
    out = df.rename(columns=rename)
    return out


def _parse_decimal(val: Any) -> Decimal:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return Decimal("0")
    if isinstance(val, Decimal):
        return val
    s = str(val).strip().replace(",", "")
    if not s:
        return Decimal("0")
    try:
        return Decimal(s)
    except InvalidOperation:
        return Decimal("0")


def _parse_date(val: Any):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if hasattr(val, "year") and hasattr(val, "month"):
        return val.date() if hasattr(val, "date") else val
    ts = pd.to_datetime(val, dayfirst=True, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.date()


def resolve_grant(using: str, *, grant_substring: str, project_substring: str | None = None) -> Grant | None:
    """Match grant by code/title or via active project code."""
    gq = (
        Grant.objects.using(using)
        .select_related("project", "donor")
        .filter(status=Grant.Status.ACTIVE)
    )
    if grant_substring:
        s = grant_substring.strip()
        g = (
            gq.filter(Q(code__icontains=s) | Q(title__icontains=s))
            .order_by("id")
            .first()
        )
        if g:
            return g
    if project_substring:
        s = project_substring.strip()
        proj = (
            Project.objects.using(using)
            .filter(Q(code__icontains=s) | Q(name__icontains=s))
            .order_by("id")
            .first()
        )
        if proj:
            return gq.filter(project_id=proj.id).order_by("id").first()
    return None


def resolve_budget_line(
    using: str,
    *,
    project_id: int | None,
    budgetcode: str,
    budget_line: str,
) -> ProjectBudgetLine | None:
    if not project_id:
        return None
    bc = (budgetcode or "").strip()
    bl = (budget_line or "").strip()
    qs = ProjectBudgetLine.objects.using(using).select_related("project_budget", "account").filter(
        project_budget__project_id=project_id
    )
    if bc:
        hit = qs.filter(category__iexact=bc).first()
        if hit:
            return hit
        hit = qs.filter(category__icontains=bc).first()
        if hit:
            return hit
    if bl:
        hit = qs.filter(category__iexact=bl).first()
        if hit:
            return hit
        hit = qs.filter(description__icontains=bl[:80]).first() if len(bl) > 3 else None
        if hit:
            return hit
    return None


def resolve_expense_account(
    using: str,
    *,
    pbl: ProjectBudgetLine | None,
    account_code_from_row: str,
    default_expense_code: str,
) -> ChartAccount:
    code = (account_code_from_row or "").strip()
    if code:
        acc = ChartAccount.objects.using(using).filter(code=code, is_active=True).first()
        if acc:
            return acc
    if pbl and pbl.account_id:
        return pbl.account
    acc = ChartAccount.objects.using(using).filter(code=default_expense_code.strip(), is_active=True).first()
    if not acc:
        raise ValueError(
            f"No expense account: row code empty, budget line has no GL, and default {default_expense_code!r} missing."
        )
    return acc


def import_gl_rows_from_dataframe(
    df: pd.DataFrame,
    *,
    using: str,
    grant: Grant,
    actor,
    bank_account: ChartAccount,
    default_expense_code: str = "5351",
    dry_run: bool = False,
) -> list[ImportRowResult]:
    """
    Each non-empty row becomes one balanced journal: Dr expense, Cr bank.
    Skips rows with no document reference and no movement; skips duplicates (same source_document_no + grant).
    """
    df = normalize_dataframe_columns(df)
    required = {"date", "debit", "credit"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Spreadsheet missing columns after normalize: {sorted(missing)}")

    currency_usd, _ = Currency.objects.using(using).get_or_create(
        code="USD",
        defaults={"name": "US Dollar", "symbol": "$", "decimal_places": 2, "status": Currency.Status.ACTIVE},
    )

    results: list[ImportRowResult] = []
    seen_docs: set[str] = set()

    for i, row in df.iterrows():
        idx = int(i) + 2  # 1-based sheet row assuming header row 1
        doc = ""
        if "document_reference" in df.columns:
            doc = str(row.get("document_reference") or "").strip()
        debit = _parse_decimal(row.get("debit"))
        credit = _parse_decimal(row.get("credit"))
        movement = max(debit, credit)

        if not doc and movement <= 0:
            results.append(ImportRowResult(idx, "", "skipped", "Empty row"))
            continue
        if movement <= 0:
            results.append(ImportRowResult(idx, doc or "", "skipped", "No debit/credit amount"))
            continue
        if not doc:
            results.append(ImportRowResult(idx, "", "skipped", "Document reference required for posting"))
            continue

        if debit <= 0 and credit > 0:
            results.append(
                ImportRowResult(idx, doc, "skipped", "Credit-only rows not imported (expected expense debits).")
            )
            continue

        amount = debit
        if amount <= 0:
            results.append(ImportRowResult(idx, doc, "skipped", "No debit amount"))
            continue

        if doc:
            key = f"{grant.id}:{doc}"
            if key in seen_docs:
                results.append(ImportRowResult(idx, doc, "skipped", "Duplicate document in file"))
                continue
            if JournalEntry.objects.using(using).filter(
                grant_id=grant.id,
                source_document_no=doc,
            ).exists():
                results.append(ImportRowResult(idx, doc, "skipped", "Already posted (source document exists)"))
                continue
            seen_docs.add(key)

        entry_date = _parse_date(row.get("date"))
        if not entry_date:
            results.append(ImportRowResult(idx, doc, "error", "Invalid or missing date"))
            continue

        desc = ""
        if "description" in df.columns:
            desc = str(row.get("description") or "").strip()
        memo = (desc[:250] if desc else (doc or f"Import row {idx}"))

        bc = str(row.get("budgetcode") or "").strip() if "budgetcode" in df.columns else ""
        bl = str(row.get("budget_line") or "").strip() if "budget_line" in df.columns else ""
        pbl = resolve_budget_line(using, project_id=grant.project_id, budgetcode=bc, budget_line=bl)

        acode = ""
        if "account_code" in df.columns:
            acode = str(row.get("account_code") or "").strip()

        try:
            expense_acc = resolve_expense_account(
                using,
                pbl=pbl,
                account_code_from_row=acode,
                default_expense_code=default_expense_code,
            )
        except ValueError as e:
            results.append(ImportRowResult(idx, doc, "error", str(e)))
            continue

        cur_code = "USD"
        if "currency" in df.columns:
            c = str(row.get("currency") or "").strip()
            if c:
                cur_code = c
        currency = Currency.objects.using(using).filter(code=cur_code).first() or currency_usd

        line_amounts: list[tuple[Decimal, Decimal]] = [
            (amount, Decimal("0")),
            (Decimal("0"), amount),
        ]
        assert_balanced_line_amounts(line_amounts=line_amounts)

        if dry_run:
            results.append(ImportRowResult(idx, doc or "(no doc)", "posted", "dry-run OK", None))
            continue

        try:
            with transaction.atomic(using=using):
                entry = JournalEntry.objects.using(using).create(
                    entry_date=entry_date,
                    posting_date=entry_date,
                    memo=memo,
                    grant=grant,
                    donor=grant.donor,
                    currency=currency,
                    status=JournalEntry.Status.DRAFT,
                    created_by=actor,
                    source_type=JournalEntry.SourceType.MANUAL,
                    journal_type="adjustment",
                    source_document_no=(doc[:120] if doc else ""),
                    reference="",
                    is_system_generated=False,
                    payment_status=JournalEntry.PaymentStatus.PAID,
                )
                ref = (doc[:60] if doc else f"JE-{entry.id:05d}")
                entry.reference = ref
                if not (entry.source_document_no or "").strip():
                    entry.source_document_no = ref[:120]
                entry.save(using=using, update_fields=["reference", "source_document_no"])

                JournalLine.objects.using(using).create(
                    entry=entry,
                    account=expense_acc,
                    grant=grant,
                    project_budget_line=pbl,
                    description=desc[:255] if desc else memo[:255],
                    debit=amount,
                    credit=Decimal("0"),
                )
                JournalLine.objects.using(using).create(
                    entry=entry,
                    account=bank_account,
                    description=desc[:255] if desc else memo[:255],
                    debit=Decimal("0"),
                    credit=amount,
                )

                entry.status = JournalEntry.Status.POSTED
                entry.posted_at = timezone.now()
                entry.posted_by = actor
                entry.source_id = entry.pk
                if entry.reference and not entry.source_document_no:
                    entry.source_document_no = entry.reference
                entry.save(using=using)

            results.append(ImportRowResult(idx, doc, "posted", "", entry.id))
        except ValidationError as exc:
            msg = (
                "; ".join(sum(exc.message_dict.values(), []))
                if hasattr(exc, "message_dict") and exc.message_dict
                else str(exc)
            )
            results.append(ImportRowResult(idx, doc, "error", msg))
        except Exception as exc:
            results.append(ImportRowResult(idx, doc, "error", str(exc)))

    return results


def read_gl_spreadsheet(path: str) -> pd.DataFrame:
    return pd.read_excel(path, engine="openpyxl")
