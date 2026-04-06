"""
Import spreadsheet rows as finance draft documents only (no GL / bank / budget impact until posted).

**Payments** imported from Excel are always created in **Draft** and must follow
Draft → Pending approval → Approved → Posted before they affect the GL.
**Receipt** imports are drafts for completion; receipts normally post directly when entered in the UI
because cash is already received.

Payment voucher drafts: Excel columns match the Payment Entry form labels (see
``payment_voucher_excel_schema.PAYMENT_VOUCHER_EXCEL_COLUMNS``). Each non-empty row requires **Payment date**
and a valid **Amount** (plain numeric: ``1000``, ``1000.00``, ``1,000.50``; no currency words or symbols).
Other fields may be blank for drafts to complete later. Legacy column keys remain accepted.
Receipt / manual journal imports keep their own column sets; **status** when present must be Draft or blank.
Posting still requires an open accounting period (enforced at post time, not on import).
Duplicate rows within one import, or rows matching an already posted transaction (same type, date,
amount, payee, external reference, and project), are rejected and listed in the import error report.
"""
from __future__ import annotations

import io
import math
import re
from decimal import Decimal, InvalidOperation
from typing import Any, BinaryIO

# Plain numeric amount after stripping thousands commas (no currency text, no spaces).
_PLAIN_AMOUNT_STR = re.compile(r"^-?\d+(\.\d+)?$")

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date

from tenant_finance.services.transaction_duplicate_detection import (
    find_posted_duplicate,
    fingerprint_from_import_row,
)


def _require_pandas():
    try:
        import pandas as pd  # noqa: F401
    except ImportError as e:
        raise RuntimeError("pandas is required for Excel import.") from e


def _read_excel_sheet(file_obj: BinaryIO) -> Any:
    _require_pandas()
    import pandas as pd

    raw = file_obj.read()
    return pd.read_excel(io.BytesIO(raw), engine="openpyxl")


def _norm_header(h: Any) -> str:
    s = re.sub(r"\s+", "_", str(h or "").strip().lower())
    s = re.sub(r"[^a-z0-9_]+", "", s)
    return s


def _normalize_df(df: Any) -> Any:
    df = df.copy()
    df.columns = [_norm_header(c) for c in df.columns]
    return df


def _cell_str(row: Any, *keys: str) -> str:
    for k in keys:
        if k in row.index and row[k] is not None:
            v = row[k]
            if hasattr(v, "item") and not isinstance(v, (str, bytes)):
                try:
                    v = v.item()
                except Exception:
                    pass
            if v is None or (isinstance(v, float) and str(v) == "nan"):
                continue
            s = str(v).strip()
            if s and s.lower() != "nan":
                return s
    return ""


def _parse_date(row: Any, *header_keys: str) -> Any:
    keys = header_keys if header_keys else ("entry_date", "voucher_date", "date", "journal_date")
    raw = _cell_str(row, *keys)
    if not raw:
        return None
    d = parse_date(raw[:10]) if len(raw) >= 10 else parse_date(raw)
    if d:
        return d
    _require_pandas()
    import pandas as pd

    for k in keys:
        if k in row.index and row[k] is not None and not (isinstance(row[k], float) and str(row[k]) == "nan"):
            try:
                ts = pd.to_datetime(row[k], errors="coerce")
                if hasattr(ts, "date") and not pd.isna(ts):
                    return ts.date()
            except Exception:
                pass
    return None


def _parse_decimal(row: Any, *keys: str) -> Decimal | None:
    raw = _cell_str(row, *keys)
    if not raw:
        return None
    try:
        return Decimal(raw.replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _is_blank_excel_value(v: Any) -> bool:
    if v is None:
        return True
    try:
        import pandas as pd

        if pd.isna(v):
            return True
    except Exception:
        pass
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return True
    if isinstance(v, str) and not v.strip():
        return True
    return False


def _parse_strict_numeric_amount(v: Any) -> tuple[Decimal | None, str | None]:
    """
    Parse a single Excel cell as a plain amount (no currency words or symbols).

    Returns (Decimal, None) on success. On failure returns (None, 'empty'|'invalid').
    Accepts typical numeric cells (int, float, Decimal) and strings like 1000, 1000.00, 1,000.50.
    Rejects values containing letters (e.g. '1000 USD', 'One thousand').
    """
    if _is_blank_excel_value(v):
        return None, "empty"
    if isinstance(v, bool):
        return None, "invalid"
    try:
        import numpy as np

        if isinstance(v, np.integer):
            return Decimal(int(v)), None
        if isinstance(v, np.floating):
            return _parse_strict_numeric_amount(float(v))
    except ImportError:
        pass
    if type(v) is int:
        return Decimal(v), None
    if isinstance(v, Decimal):
        if not v.is_finite():
            return None, "invalid"
        return v, None
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None, "invalid"
        try:
            d = Decimal(str(v))
        except (InvalidOperation, ValueError):
            return None, "invalid"
        if not d.is_finite():
            return None, "invalid"
        return d, None
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        if not s:
            return None, "empty"
        if any(c.isalpha() for c in s):
            return None, "invalid"
        if not _PLAIN_AMOUNT_STR.fullmatch(s):
            return None, "invalid"
        try:
            return Decimal(s), None
        except (InvalidOperation, ValueError):
            return None, "invalid"
    return None, "invalid"


def _parse_strict_amount_row(row: Any, *keys: str) -> tuple[Decimal | None, str | None]:
    """
    First non-blank cell among keys is parsed as amount.
    Returns (Decimal, None) on success, or (None, 'empty'|'invalid').
    """
    raw: Any = None
    for k in keys:
        if k not in row.index:
            continue
        cell = row[k]
        if _is_blank_excel_value(cell):
            continue
        raw = cell
        break
    if raw is None:
        return None, "empty"
    return _parse_strict_numeric_amount(raw)


def _amount_invalid_for_voucher_row(
    *,
    parsed: Decimal | None,
    parse_err: str | None,
) -> bool:
    """True if amount is missing, non-numeric, non-positive, or otherwise unusable."""
    if parse_err:
        return True
    if parsed is None:
        return True
    if parsed <= 0:
        return True
    return False


def _resolve_chart_account(using: str, code: str):
    """Resolve by numeric primary key first, then by account code (matches Payment Entry account pickers)."""
    if not code:
        return None
    from tenant_finance.models import ChartAccount

    s = code.strip()
    if s.isdigit():
        by_id = ChartAccount.objects.using(using).filter(pk=int(s), is_active=True).first()
        if by_id:
            return by_id
    return ChartAccount.objects.using(using).filter(code__iexact=s, is_active=True).first()


def _payment_field_keys(field: str) -> tuple[str, ...]:
    """Normalized Excel header keys for one Payment Entry field (locale label + legacy aliases)."""
    from django.utils.translation import gettext as _

    from tenant_finance.services.payment_voucher_excel_schema import (
        PAYMENT_VOUCHER_EXCEL_COLUMNS,
        PAYMENT_VOUCHER_FIELD_ORDER,
        PAYMENT_VOUCHER_LEGACY_ALIASES,
    )

    idx = PAYMENT_VOUCHER_FIELD_ORDER.index(field)
    label = PAYMENT_VOUCHER_EXCEL_COLUMNS[idx]
    merged = [_norm_header(str(_(label)))]
    merged.extend(PAYMENT_VOUCHER_LEGACY_ALIASES.get(field, ()))
    seen: set[str] = set()
    out: list[str] = []
    for k in merged:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return tuple(out)


def _project_budget_line_for_grant_budget(using: str, project, bl) -> Any:
    """Map grant BudgetLine to ProjectBudgetLine by category code when project budget exists."""
    if not project or not bl:
        return None
    from tenant_grants.models import ProjectBudget, ProjectBudgetLine

    pb = ProjectBudget.objects.using(using).filter(project=project).first()
    if not pb:
        return None
    code = (bl.budget_code or "").strip()
    if not code:
        return None
    return ProjectBudgetLine.objects.using(using).filter(project_budget=pb, category__iexact=code).first()


def _resolve_budget_line_payment(using: str, grant, row: Any, budget_keys: tuple[str, ...]):
    from tenant_grants.models import BudgetLine

    raw = _cell_str(row, *budget_keys)
    if not raw:
        return None
    if raw.isdigit():
        bl = BudgetLine.objects.using(using).filter(pk=int(raw)).select_related("grant").first()
        if bl and grant and bl.grant_id != grant.id:
            return None
        return bl
    if grant:
        return (
            BudgetLine.objects.using(using)
            .filter(grant=grant, budget_code__iexact=raw.strip(), status=BudgetLine.Status.ACTIVE)
            .first()
        )
    return None


def _resolve_grant(using: str, code_or_id: str):
    if not code_or_id:
        return None
    from tenant_grants.models import Grant

    s = code_or_id.strip()
    if s.isdigit():
        return Grant.objects.using(using).filter(pk=int(s)).first()
    return Grant.objects.using(using).filter(code__iexact=s).first()


def _resolve_project(using: str, code_or_id: str):
    if not code_or_id:
        return None
    from tenant_grants.models import Project

    s = code_or_id.strip()
    if s.isdigit():
        return Project.objects.using(using).filter(pk=int(s)).first()
    return Project.objects.using(using).filter(code__iexact=s).first()


def _default_grant_for_project(using: str, project):
    """If the project has exactly one active grant, return it (else None)."""
    from tenant_grants.models import Grant

    qs = (
        Grant.objects.using(using)
        .filter(project=project, status=Grant.Status.ACTIVE)
        .order_by("code")
    )
    first = qs.first()
    if not first:
        return None
    second = qs.exclude(pk=first.pk).first()
    return first if second is None else None


def _draft_status_ok(row: Any, row_no: int) -> str | None:
    """If a status column is present, it must be Draft. Returns error message or None."""
    raw = _cell_str(row, "status", "voucher_status", "entry_status")
    if not raw:
        return None
    s = raw.strip().lower().replace(" ", "_")
    if s in ("draft", "drf", "d"):
        return None
    if s in ("posted", "post", "pending_approval", "pending", "approved", "submitted"):
        return f"Row {row_no}: status must be Draft for import (found {raw!r})."
    return f"Row {row_no}: unrecognized status {raw!r}; use Draft or leave blank."


def _resolve_budget_line(using: str, grant, row: Any):
    from tenant_grants.models import BudgetLine

    bid = _cell_str(row, "budget_line_id", "budgetline_id")
    if bid.isdigit():
        bl = BudgetLine.objects.using(using).filter(pk=int(bid)).select_related("grant").first()
        if bl and grant and bl.grant_id != grant.id:
            return None
        return bl
    bcode = _cell_str(row, "budget_code", "budgetcode")
    if bcode and grant:
        return (
            BudgetLine.objects.using(using)
            .filter(grant=grant, budget_code__iexact=bcode.strip(), status=BudgetLine.Status.ACTIVE)
            .first()
        )
    return None


def import_payment_voucher_drafts_from_excel(*, using: str, user, file_obj: BinaryIO) -> dict[str, Any]:
    from tenant_finance.models import AuditLog, JournalEntry, JournalLine
    from tenant_finance.services.payment_voucher_excel_schema import (
        PAYMENT_VOUCHER_FIELD_ORDER,
        PV_FIELD_AMOUNT,
        PV_FIELD_BANK_ACCOUNT,
        PV_FIELD_BUDGET_CODE,
        PV_FIELD_DESCRIPTION,
        PV_FIELD_ENTRY_DATE,
        PV_FIELD_EXPENSE_ACCOUNT,
        PV_FIELD_GRANT,
        PV_FIELD_OPTIONAL_NOTE,
        PV_FIELD_PAYEE,
        PV_FIELD_PAYMENT_METHOD,
        PV_FIELD_PROJECT,
        PV_FIELD_REFERENCE,
        PV_FIELD_SUPPORTING_ATTACHMENT,
    )

    def _row_has_any_value(r: Any) -> bool:
        for field in PAYMENT_VOUCHER_FIELD_ORDER:
            if field == PV_FIELD_SUPPORTING_ATTACHMENT:
                continue
            if _cell_str(r, *_payment_field_keys(field)):
                return True
        return False

    df = _normalize_df(_read_excel_sheet(file_obj))
    today = timezone.localdate()
    created = 0
    row_errors: list[str] = []
    amount_issue_rows: list[int] = []

    for idx, row in df.iterrows():
        row_no = int(idx) + 2
        try:
            st_err = _draft_status_ok(row, row_no)
            if st_err:
                row_errors.append(st_err)
                continue

            if not _row_has_any_value(row):
                continue

            entry_date = _parse_date(row, *_payment_field_keys(PV_FIELD_ENTRY_DATE))
            if not entry_date:
                row_errors.append(f"Row {row_no}: Payment date is required.")
                continue
            if entry_date > today:
                row_errors.append(f"Row {row_no}: date cannot be in the future.")
                continue

            desc = _cell_str(row, *_payment_field_keys(PV_FIELD_DESCRIPTION))
            note = _cell_str(row, *_payment_field_keys(PV_FIELD_OPTIONAL_NOTE))
            proj_key = _cell_str(row, *_payment_field_keys(PV_FIELD_PROJECT))
            project = _resolve_project(using, proj_key) if proj_key else None
            if proj_key and not project:
                row_errors.append(f"Row {row_no}: project code or ID was not found.")
                continue

            grant_key = _cell_str(row, *_payment_field_keys(PV_FIELD_GRANT))
            grant_in = _resolve_grant(using, grant_key) if grant_key else None
            if grant_in and not project:
                project = grant_in.project
            if grant_in and project and grant_in.project_id != project.id:
                row_errors.append(
                    f"Row {row_no}: grant {grant_in.code!r} does not belong to project {project.code!r}."
                )
                continue
            grant = grant_in or ( _default_grant_for_project(using, project) if project else None )

            memo = desc
            if project and grant is None:
                memo = (f"[{project.code}] {desc}".strip())[:255]
            if note:
                memo = (f"{memo}\n{note}" if memo else note)[:255]

            payee = _cell_str(row, *_payment_field_keys(PV_FIELD_PAYEE))
            pay_m = _cell_str(row, *_payment_field_keys(PV_FIELD_PAYMENT_METHOD)) or ""
            amt_parsed, amt_err = _parse_strict_amount_row(row, *_payment_field_keys(PV_FIELD_AMOUNT))
            # Reject non-numeric amounts; missing/zero amounts create an incomplete draft (no lines until completed).
            if amt_err == "invalid":
                row_errors.append(f"Amount invalid in row {row_no}")
                amount_issue_rows.append(row_no)
                continue
            amt: Decimal | None = amt_parsed if (amt_parsed is not None and amt_parsed > 0) else None

            budget_raw = _cell_str(row, *_payment_field_keys(PV_FIELD_BUDGET_CODE))
            if (not grant) and budget_raw:
                row_errors.append(
                    f"Row {row_no}: Budget code requires a grant; specify Grant or a project with a single active grant."
                )
                continue

            bl = _resolve_budget_line_payment(using, grant, row, _payment_field_keys(PV_FIELD_BUDGET_CODE)) if grant else None
            expense_ac = _resolve_chart_account(using, _cell_str(row, *_payment_field_keys(PV_FIELD_EXPENSE_ACCOUNT)))
            bank_ac = _resolve_chart_account(using, _cell_str(row, *_payment_field_keys(PV_FIELD_BANK_ACCOUNT)))
            if bl and bl.account_id and not expense_ac:
                expense_ac = bl.account

            ext_ref = _cell_str(row, *_payment_field_keys(PV_FIELD_REFERENCE))
            fp_ref = ext_ref or f"import-row-{row_no}"
            fp = fingerprint_from_import_row(
                source_type=str(JournalEntry.SourceType.PAYMENT_VOUCHER),
                journal_type="payment_voucher",
                receipt_stream="",
                entry_date=entry_date,
                amount=amt,
                payee_name=payee,
                source_document_no=fp_ref[:120],
                reference="",
                project_id=project.pk if project else None,
            )
            dup = find_posted_duplicate(using=using, fingerprint=fp)
            if dup:
                dref = (dup.reference or dup.source_document_no or "").strip() or f"#{dup.pk}"
                row_errors.append(f"Row {row_no}: duplicate of already posted transaction ({dref}).")
                continue
            with transaction.atomic(using=using):
                entry = JournalEntry.objects.using(using).create(
                    entry_date=entry_date,
                    memo=(memo or "")[:255],
                    grant=grant,
                    project=project,
                    status=JournalEntry.Status.DRAFT,
                    created_by=user,
                    payee_name=payee[:255] if payee else "",
                    payee_ref_type=JournalEntry.PayeeReferenceType.MANUAL if payee else "",
                    payment_method=pay_m[:40],
                    source=JournalEntry.SourceType.PAYMENT_VOUCHER,
                    source_type=JournalEntry.SourceType.PAYMENT_VOUCHER,
                    journal_type="payment_voucher",
                    is_system_generated=True,
                )
                entry.reference = f"PV-{entry.id:05d}"
                entry.source_document_no = ext_ref[:120] if ext_ref else entry.reference
                entry.source_id = entry.pk
                entry.save(
                    using=using,
                    update_fields=["reference", "source_document_no", "source_id"],
                )
                pbl = _project_budget_line_for_grant_budget(using, project, bl) if project and bl else None
                if expense_ac and bank_ac and amt and amt > 0:
                    JournalLine.objects.using(using).create(
                        entry=entry,
                        account=expense_ac,
                        description=(memo or desc or "")[:255],
                        debit=amt,
                        credit=Decimal("0"),
                        grant=grant,
                        project_budget_line=pbl,
                    )
                    JournalLine.objects.using(using).create(
                        entry=entry,
                        account=bank_ac,
                        description=(memo or desc or "")[:255],
                        debit=Decimal("0"),
                        credit=amt,
                        grant=grant,
                    )
                from tenant_finance.services.payment_voucher_draft_completeness import (
                    refresh_payment_voucher_draft_status,
                )

                entry.refresh_from_db()
                refresh_payment_voucher_draft_status(using=using, entry=entry)
                try:
                    AuditLog.objects.using(using).create(
                        model_name="journalentry",
                        object_id=entry.id,
                        action=AuditLog.Action.CREATE,
                        user_id=getattr(user, "id", None),
                        username=(getattr(user, "full_name", "") or getattr(user, "email", "") or ""),
                        summary=f"Imported draft payment voucher {entry.reference}",
                    )
                except Exception:
                    pass
            created += 1
        except Exception as exc:
            row_errors.append(f"Row {row_no}: {exc}")

    return {"created": created, "errors": row_errors, "amount_issue_rows": amount_issue_rows}


def import_receipt_voucher_drafts_from_excel(*, using: str, user, file_obj: BinaryIO) -> dict[str, Any]:
    from tenant_finance.models import AuditLog, JournalEntry, JournalLine

    df = _normalize_df(_read_excel_sheet(file_obj))
    today = timezone.localdate()
    created = 0
    row_errors: list[str] = []
    batch_keys: set[tuple] = set()
    amount_issue_rows: list[int] = []

    for idx, row in df.iterrows():
        row_no = int(idx) + 2
        try:
            st_err = _draft_status_ok(row, row_no)
            if st_err:
                row_errors.append(st_err)
                continue

            desc = _cell_str(row, "memo", "description", "purpose")
            proj_key = _cell_str(row, "project_code", "project_id", "project")
            entry_date = _parse_date(row)
            if not entry_date and not desc and not proj_key:
                continue
            if not entry_date:
                row_errors.append(f"Row {row_no}: date is required.")
                continue
            if entry_date > today:
                row_errors.append(f"Row {row_no}: date cannot be in the future.")
                continue
            if not desc:
                row_errors.append(f"Row {row_no}: description is required.")
                continue
            project = _resolve_project(using, proj_key)
            if not project:
                row_errors.append(f"Row {row_no}: project is required (project_code or project_id).")
                continue

            grant_in = _resolve_grant(using, _cell_str(row, "grant_code", "grant_id", "grant"))
            if grant_in and grant_in.project_id != project.id:
                row_errors.append(
                    f"Row {row_no}: grant {grant_in.code!r} does not belong to project {project.code!r}."
                )
                continue
            grant = grant_in or _default_grant_for_project(using, project)
            memo = desc
            if grant is None:
                prefix = f"[{project.code}] "
                memo = f"{prefix}{desc}"[:255]

            received = _cell_str(row, "received_from", "payee", "payer")
            rmethod = _cell_str(row, "receipt_method", "method") or ""
            rtype = _cell_str(row, "receipt_type", "type") or "other_income"
            if rtype not in {"grant_funding", "cashbook", "other_income"}:
                rtype = "other_income"
            amt_parsed, amt_err = _parse_strict_amount_row(row, "amount", "total")
            if _amount_invalid_for_voucher_row(parsed=amt_parsed, parse_err=amt_err):
                row_errors.append(f"Amount missing or invalid in row {row_no}")
                amount_issue_rows.append(row_no)
                continue
            amt = amt_parsed  # type: ignore[assignment]
            if (not grant) and (
                _cell_str(row, "budget_line_id", "budgetline_id") or _cell_str(row, "budget_code", "budgetcode")
            ):
                row_errors.append(
                    f"Row {row_no}: budget line or budget_code requires a grant; specify grant_code or use a single active grant on the project."
                )
                continue
            dep = _resolve_chart_account(using, _cell_str(row, "deposit_gl_code", "deposit_account", "bank_gl_code"))
            credit_ac = _resolve_chart_account(
                using,
                _cell_str(row, "credit_gl_code", "income_gl_code", "income_account"),
            )
            valid_rs = {"grant_funding", "other_income", "cashbook"}
            receipt_stream = rtype if rtype in valid_rs else ""
            header_grant = grant if rtype == "grant_funding" else None
            ext = _cell_str(row, "reference_no", "external_reference")
            fp = fingerprint_from_import_row(
                source_type=str(JournalEntry.SourceType.RECEIPT_VOUCHER),
                journal_type="receipt_voucher",
                receipt_stream=receipt_stream,
                entry_date=entry_date,
                amount=amt,
                payee_name=received,
                source_document_no=ext[:120] if ext else "",
                reference="",
                project_id=project.pk,
            )
            if fp in batch_keys:
                row_errors.append(
                    f"Row {row_no}: duplicate row in this file (same type, date, amount, payee, reference, project)."
                )
                continue
            dup = find_posted_duplicate(using=using, fingerprint=fp)
            if dup:
                dref = (dup.reference or dup.source_document_no or "").strip() or f"#{dup.pk}"
                row_errors.append(f"Row {row_no}: duplicate of already posted transaction ({dref}).")
                continue
            batch_keys.add(fp)
            with transaction.atomic(using=using):
                entry = JournalEntry.objects.using(using).create(
                    entry_date=entry_date,
                    memo=memo[:255],
                    grant=header_grant,
                    project=project,
                    status=JournalEntry.Status.DRAFT,
                    created_by=user,
                    payment_method=rmethod[:40],
                    payee_name=received[:255] if received else "",
                    payee_ref_type=JournalEntry.PayeeReferenceType.MANUAL if received else "",
                    source=JournalEntry.SourceType.RECEIPT_VOUCHER,
                    source_type=JournalEntry.SourceType.RECEIPT_VOUCHER,
                    journal_type="receipt_voucher",
                    is_system_generated=True,
                    receipt_stream=receipt_stream,
                )
                ref = f"RV-{entry.id:05d}"
                entry.reference = ref
                entry.source_document_no = ext[:120] if ext else ref
                entry.source_id = entry.pk
                entry.save(
                    using=using,
                    update_fields=["reference", "source_document_no", "source_id"],
                )
                line_grant = grant if rtype == "grant_funding" else None
                JournalLine.objects.using(using).create(
                    entry=entry,
                    account=dep,
                    description=memo[:255],
                    debit=amt,
                    credit=Decimal("0"),
                    grant=line_grant,
                )
                JournalLine.objects.using(using).create(
                    entry=entry,
                    account=credit_ac,
                    description=memo[:255],
                    debit=Decimal("0"),
                    credit=amt,
                    grant=line_grant,
                )
                try:
                    AuditLog.objects.using(using).create(
                        model_name="journalentry",
                        object_id=entry.id,
                        action=AuditLog.Action.CREATE,
                        user_id=getattr(user, "id", None),
                        username=(getattr(user, "full_name", "") or getattr(user, "email", "") or ""),
                        summary=f"Imported draft receipt voucher {entry.reference}",
                    )
                except Exception:
                    pass
            created += 1
        except Exception as exc:
            row_errors.append(f"Row {row_no}: {exc}")

    return {"created": created, "errors": row_errors, "amount_issue_rows": amount_issue_rows}


def import_manual_journal_drafts_from_excel(*, using: str, user, file_obj: BinaryIO) -> dict[str, Any]:
    from tenant_finance.models import AuditLog, JournalEntry, JournalLine
    from tenant_finance.services.manual_journal_validation import map_journal_type_to_source_type

    df = _normalize_df(_read_excel_sheet(file_obj))
    today = timezone.localdate()
    created = 0
    row_errors: list[str] = []
    batch_keys: set[tuple] = set()

    for idx, row in df.iterrows():
        row_no = int(idx) + 2
        try:
            st_err = _draft_status_ok(row, row_no)
            if st_err:
                row_errors.append(st_err)
                continue

            desc = _cell_str(row, "memo", "description", "purpose")
            proj_key = _cell_str(row, "project_code", "project_id", "project")
            entry_date = _parse_date(row)
            if not entry_date and not desc and not proj_key:
                continue
            if not entry_date:
                row_errors.append(f"Row {row_no}: date is required.")
                continue
            posting_raw = _cell_str(row, "posting_date")
            posting_date = parse_date(posting_raw[:10]) if posting_raw and len(posting_raw) >= 10 else None
            if not posting_date:
                posting_date = entry_date
            if entry_date > today:
                row_errors.append(f"Row {row_no}: date cannot be in the future.")
                continue
            if not desc:
                row_errors.append(f"Row {row_no}: description is required.")
                continue
            project = _resolve_project(using, proj_key)
            if not project:
                row_errors.append(f"Row {row_no}: project is required (project_code or project_id).")
                continue

            grant_in = _resolve_grant(using, _cell_str(row, "grant_code", "grant_id", "grant"))
            if grant_in and grant_in.project_id != project.id:
                row_errors.append(
                    f"Row {row_no}: grant {grant_in.code!r} does not belong to project {project.code!r}."
                )
                continue
            grant = grant_in or _default_grant_for_project(using, project)
            memo = desc
            if grant is None:
                prefix = f"[{project.code}] "
                memo = f"{prefix}{desc}"[:255]

            jt = _cell_str(row, "journal_type", "type") or "adjustment"
            if (not grant) and (
                _cell_str(row, "budget_line_id", "budgetline_id") or _cell_str(row, "budget_code", "budgetcode")
            ):
                row_errors.append(
                    f"Row {row_no}: budget line or budget_code requires a grant; specify grant_code or use a single active grant on the project."
                )
                continue
            st_manual = map_journal_type_to_source_type(jt)
            ac1 = _resolve_chart_account(using, _cell_str(row, "account_1", "line1_account", "debit_account"))
            ac2 = _resolve_chart_account(using, _cell_str(row, "account_2", "line2_account", "credit_account"))
            d1 = _parse_decimal(row, "debit_1", "line1_debit")
            c1 = _parse_decimal(row, "credit_1", "line1_credit")
            d2 = _parse_decimal(row, "debit_2", "line2_debit")
            c2 = _parse_decimal(row, "credit_2", "line2_credit")
            if d1 is None:
                d1 = Decimal("0")
            if c1 is None:
                c1 = Decimal("0")
            if d2 is None:
                d2 = Decimal("0")
            if c2 is None:
                c2 = Decimal("0")
            ext_ref = _cell_str(row, "reference_no", "external_reference")
            jt_stored = (jt[:40] if jt else "").strip()
            amt_total = (d1 + d2).quantize(Decimal("0.01"))
            fp = fingerprint_from_import_row(
                source_type=str(st_manual),
                journal_type=jt_stored.lower(),
                receipt_stream="",
                entry_date=entry_date,
                amount=amt_total,
                payee_name="",
                source_document_no=ext_ref[:120] if ext_ref else "",
                reference="",
                project_id=project.pk,
            )
            if fp in batch_keys:
                row_errors.append(
                    f"Row {row_no}: duplicate row in this file (same type, date, amount, payee, reference, project)."
                )
                continue
            dup = find_posted_duplicate(using=using, fingerprint=fp)
            if dup:
                dref = (dup.reference or dup.source_document_no or "").strip() or f"#{dup.pk}"
                row_errors.append(f"Row {row_no}: duplicate of already posted transaction ({dref}).")
                continue
            batch_keys.add(fp)
            with transaction.atomic(using=using):
                entry = JournalEntry.objects.using(using).create(
                    entry_date=entry_date,
                    posting_date=posting_date,
                    memo=memo[:255],
                    grant=grant,
                    project=project,
                    status=JournalEntry.Status.DRAFT,
                    created_by=user,
                    journal_type=jt_stored,
                    source="manual",
                    source_type=st_manual,
                    source_document_no=ext_ref[:120] if ext_ref else "",
                    is_system_generated=False,
                )
                JournalLine.objects.using(using).create(
                    entry=entry,
                    account=ac1,
                    description=memo[:255],
                    debit=d1,
                    credit=c1,
                    grant_id=grant.pk if grant else None,
                )
                JournalLine.objects.using(using).create(
                    entry=entry,
                    account=ac2,
                    description=memo[:255],
                    debit=d2,
                    credit=c2,
                    grant_id=grant.pk if grant else None,
                )
                try:
                    AuditLog.objects.using(using).create(
                        model_name="journalentry",
                        object_id=entry.id,
                        action=AuditLog.Action.CREATE,
                        user_id=getattr(user, "id", None),
                        username=(getattr(user, "full_name", "") or getattr(user, "email", "") or ""),
                        summary="Imported draft manual journal",
                    )
                except Exception:
                    pass
            created += 1
        except Exception as exc:
            row_errors.append(f"Row {row_no}: {exc}")

    return {"created": created, "errors": row_errors}


def excel_template_bytes(*, kind: str) -> tuple[bytes, str]:
    """Return (xlsx bytes, filename). kind: payment | receipt | journal."""
    _require_pandas()
    import pandas as pd

    if kind == "payment":
        from tenant_finance.services.payment_voucher_excel_schema import payment_voucher_excel_header_strings

        cols = payment_voucher_excel_header_strings()
    elif kind == "receipt":
        cols = [
            "entry_date",
            "project_code",
            "description",
            "status",
            "amount",
            "received_from",
            "receipt_method",
            "receipt_type",
            "deposit_gl_code",
            "credit_gl_code",
            "grant_code",
            "budget_line_id",
            "budget_code",
            "reference_no",
        ]
    else:
        cols = [
            "entry_date",
            "project_code",
            "description",
            "status",
            "reference_no",
            "posting_date",
            "journal_type",
            "grant_code",
            "budget_line_id",
            "budget_code",
            "account_1",
            "debit_1",
            "credit_1",
            "account_2",
            "debit_2",
            "credit_2",
        ]
    df = pd.DataFrame(columns=cols)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Drafts")
    buf.seek(0)
    name = f"draft_{kind}_import_template.xlsx"
    return buf.read(), name
