"""
General Ledger Excel export (pandas + XlsxWriter).

Layout matches org import/export spec: centered header block, table column order,
opening-based running balance, grouping Grant → Budget line, grant subtotals, grand total.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import BinaryIO, Sequence

import pandas as pd
import xlsxwriter
from django.db.models import BigIntegerField, F, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from tenant_finance.services.financial_reporting import (
    journal_entry_user_document_reference,
    posted_journal_lines,
    restrict_journal_lines_by_grant_scope,
)


@dataclass(frozen=True)
class GeneralLedgerFilters:
    period_start: date
    period_end: date
    grant_id: int | None = None
    project_id: int | None = None
    donor_id: int | None = None
    account_id: int | None = None


@dataclass(frozen=True)
class GeneralLedgerHeaderContext:
    """Centered header rows below the title (full-width merged)."""

    project_title: str
    donor_name: str
    period_start: date
    period_end: date
    generated_at: datetime
    currency_label: str


# Exact column order for the detail table (headers as specified).
TABLE_COLUMNS: Sequence[str] = (
    "Date",
    "Journal Ref",
    "Account code",
    "Account name",
    "Grant",
    "Donor",
    "Budgetcode",
    "Budget line",
    "Description",
    "Debit",
    "Credit",
    "Running balance",
    "Currency",
    "Payee",
    "Document reference",
)

TEXT_HEADER_COLS = frozenset(
    {
        "Date",
        "Journal Ref",
        "Account code",
        "Account name",
        "Grant",
        "Donor",
        "Budgetcode",
        "Budget line",
        "Description",
        "Currency",
        "Payee",
        "Document reference",
    }
)
NUM_HEADER_COLS = frozenset({"Debit", "Credit", "Running balance"})


def _pick_logo_path(org_settings) -> str | None:
    if org_settings is None:
        return None
    for attr in ("report_logo", "organization_logo", "system_logo"):
        f = getattr(org_settings, attr, None)
        if f and getattr(f, "name", None):
            try:
                p = Path(f.path)
                if p.is_file():
                    return str(p)
            except Exception:
                continue
    return None


def _decimal_or_zero(v) -> Decimal:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return Decimal("0")
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def _normalize_debit_credit(debit: Decimal, credit: Decimal) -> tuple[Decimal, Decimal]:
    """Each row shows either debit or credit (not both non-zero)."""
    d = _decimal_or_zero(debit)
    c = _decimal_or_zero(credit)
    if d > 0 and c > 0:
        net = d - c
        if net >= 0:
            return net, Decimal("0")
        return Decimal("0"), -net
    return d, c


def _filtered_journal_lines_qs(using: str, filters: GeneralLedgerFilters, *, user=None):
    """Posted lines with grant scope and dimension filters; no date range yet."""
    from tenant_grants.models import Grant

    qs = posted_journal_lines(using).annotate(
        eff_grant_id=Coalesce(F("grant_id"), F("entry__grant_id"), output_field=BigIntegerField()),
    )
    if user is not None:
        qs = restrict_journal_lines_by_grant_scope(qs, user, using)
    if filters.grant_id is not None:
        qs = qs.filter(eff_grant_id=filters.grant_id)
    if filters.project_id is not None:
        gids = list(
            Grant.objects.using(using).filter(project_id=filters.project_id).values_list("id", flat=True)
        )
        qs = qs.filter(eff_grant_id__in=gids) if gids else qs.none()
    if filters.donor_id is not None:
        did = filters.donor_id
        qs = qs.filter(
            Q(entry__donor_id=did)
            | Q(entry__grant__donor_id=did)
            | Q(grant__donor_id=did)
        )
    if filters.account_id is not None:
        qs = qs.filter(account_id=filters.account_id)
    return qs


def compute_opening_balance_net(using: str, filters: GeneralLedgerFilters, *, user=None) -> Decimal:
    """Net movement (debit − credit) for all matching posted lines strictly before period_start."""
    qs = _filtered_journal_lines_qs(using, filters, user=user).filter(gl_date__lt=filters.period_start)
    agg = qs.aggregate(td=Sum("debit"), tc=Sum("credit"))
    td = agg.get("td") or Decimal("0")
    tc = agg.get("tc") or Decimal("0")
    return _decimal_or_zero(td) - _decimal_or_zero(tc)


def build_header_context(
    filters: GeneralLedgerFilters,
    using: str,
    df: pd.DataFrame,
    *,
    org_settings=None,
) -> GeneralLedgerHeaderContext:
    from tenant_grants.models import Donor, Grant, Project

    if filters.project_id:
        p = Project.objects.using(using).filter(pk=filters.project_id).first()
        project_title = f"{p.code} — {p.name}" if p else str(filters.project_id)
    elif not df.empty and "Grant" in df.columns:
        # Infer from data: single project via grant’s project name on lines is not stored per row;
        # use unique count of grant labels if single grant points to one project.
        grants = df["Grant"].dropna().unique()
        if len(grants) == 1:
            gid = df["_grant_id"].dropna().unique()
            if len(gid) == 1:
                g = Grant.objects.using(using).filter(pk=int(gid[0])).select_related("project").first()
                if g and g.project_id:
                    project_title = f"{g.project.code} — {g.project.name}"
                else:
                    project_title = "—"
            else:
                project_title = "Various"
        else:
            project_title = "Various / All"
    else:
        project_title = "All projects"

    if filters.donor_id:
        d = Donor.objects.using(using).filter(pk=filters.donor_id).first()
        donor_name = d.name if d else str(filters.donor_id)
    elif not df.empty and "Donor" in df.columns:
        donors = [x for x in df["Donor"].dropna().unique() if str(x).strip()]
        donor_name = donors[0] if len(donors) == 1 else ("Various / All" if donors else "—")
    else:
        donor_name = "—"

    cur = None
    if org_settings and getattr(org_settings, "default_currency_id", None):
        c = org_settings.default_currency
        if c:
            cur = (c.code or "").strip()
    if not df.empty and "Currency" in df.columns:
        codes = {str(x).strip() for x in df["Currency"].dropna() if str(x).strip()}
        if len(codes) == 1:
            cur = next(iter(codes))
        elif len(codes) > 1:
            cur = "Various (see rows)"
    currency_label = cur or "—"

    return GeneralLedgerHeaderContext(
        project_title=project_title,
        donor_name=donor_name,
        period_start=filters.period_start,
        period_end=filters.period_end,
        generated_at=timezone.localtime(timezone.now()),
        currency_label=currency_label,
    )


def fetch_general_ledger_rows(
    using: str,
    filters: GeneralLedgerFilters,
    *,
    user=None,
) -> tuple[pd.DataFrame, Decimal]:
    """
    Period lines as DataFrame (sorted Grant → Budget line → date) and opening net balance.
    """
    qs = (
        _filtered_journal_lines_qs(using, filters, user=user)
        .filter(gl_date__gte=filters.period_start, gl_date__lte=filters.period_end)
        .select_related(
            "account",
            "entry",
            "entry__currency",
            "entry__grant",
            "entry__grant__project",
            "entry__donor",
            "grant",
            "grant__project",
            "grant__donor",
            "project_budget_line",
            "project_budget_line__project_budget",
        )
        .order_by("gl_date", "entry_id", "id")
    )

    opening = compute_opening_balance_net(using, filters, user=user)

    from tenant_grants.models import BudgetLine

    lines_list = list(qs)
    bl_pairs: set[tuple[int, int]] = set()
    for line in lines_list:
        ent = line.entry
        eg = line.grant if line.grant_id else ent.grant
        if eg and line.account_id:
            bl_pairs.add((eg.id, line.account_id))
    grant_budget_lines: dict[tuple[int, int], BudgetLine] = {}
    if bl_pairs:
        q_bl = Q()
        for gid, aid in bl_pairs:
            q_bl |= Q(grant_id=gid, account_id=aid)
        for bl in (
            BudgetLine.objects.using(using)
            .filter(q_bl, status=BudgetLine.Status.ACTIVE)
            .only("grant_id", "account_id", "budget_code", "category", "description")
        ):
            grant_budget_lines[(bl.grant_id, bl.account_id)] = bl

    rows: list[dict] = []
    for line in lines_list:
        entry = line.entry
        eff_grant = line.grant if line.grant_id else entry.grant
        donor = entry.donor if entry.donor_id else (eff_grant.donor if eff_grant else None)
        pbl = line.project_budget_line
        budget_code = ""
        budget_line = ""
        bl_sort = "\xff" * 8  # sort unassigned last
        if pbl:
            budget_code = (pbl.category or "").strip()
            budget_line = (pbl.category or "").strip()
            if (pbl.description or "").strip():
                budget_line = f"{budget_line} — {pbl.description.strip()}" if budget_line else pbl.description.strip()
            pbname = (pbl.project_budget.name or "").strip() if pbl.project_budget_id else ""
            bl_sort = f"{pbname}\t{budget_line}\t{pbl.pk}"
        elif eff_grant and line.account_id:
            gbl = grant_budget_lines.get((eff_grant.id, line.account_id))
            if gbl:
                budget_code = (gbl.budget_code or "").strip()
                cat = (gbl.category or "").strip()
                dsc = (gbl.description or "").strip()
                if cat and dsc:
                    budget_line = f"{cat} — {dsc}"
                else:
                    budget_line = cat or dsc or "—"
                bl_sort = f"{budget_code}\t{budget_line}\t{gbl.pk}"

        ref = (entry.reference or "").strip()
        if not ref:
            ref = f"JE-{entry.id:05d}"

        cur = ""
        if entry.currency_id:
            cur = (entry.currency.code or "").strip()

        doc_ref = journal_entry_user_document_reference(entry) or ""

        grant_sort = ""
        grant_label = "— No grant / Organization"
        grant_id = None
        if eff_grant:
            grant_id = eff_grant.id
            grant_sort = f"{eff_grant.code or ''}\t{eff_grant.id}"
            grant_label = f"{eff_grant.code} — {eff_grant.title}".strip(" —")

        d, c = _normalize_debit_credit(line.debit, line.credit)

        payee = (getattr(entry, "payee_name", "") or "").strip()

        rows.append(
            {
                "_grant_sort": grant_sort,
                "_grant_id": grant_id,
                "_grant_label": grant_label,
                "_budget_sort": bl_sort,
                "_budget_line_label": budget_line or "— Unassigned",
                "Date": line.gl_date,
                "Journal Ref": ref,
                "Account code": (line.account.code or "").strip(),
                "Account name": (line.account.name or "").strip(),
                "Grant": grant_label,
                "Donor": donor.name if donor else "",
                "Budgetcode": budget_code,
                "Budget line": budget_line or "—",
                "Description": (line.description or "").strip(),
                "Debit": d,
                "Credit": c,
                "Currency": cur,
                "Payee": payee,
                "Document reference": doc_ref,
            }
        )

    base_cols = [
        "_grant_sort",
        "_grant_id",
        "_grant_label",
        "_budget_sort",
        "_budget_line_label",
    ] + list(TABLE_COLUMNS)

    if not rows:
        return pd.DataFrame(columns=base_cols + ["Running balance"]), opening

    df = pd.DataFrame(rows)
    df = df.sort_values(
        by=["_grant_sort", "_budget_sort", "Date", "Journal Ref", "Account code"],
        kind="mergesort",
    ).reset_index(drop=True)

    run = opening
    balances: list[Decimal] = []
    for _, r in df.iterrows():
        run = run + _decimal_or_zero(r["Debit"]) - _decimal_or_zero(r["Credit"])
        balances.append(run)
    df["Running balance"] = balances
    return df, opening


def _logo_insert_options(logo_path: str, max_height_px: float = 72.0, max_width_px: float = 420.0) -> dict:
    """Equal x/y scale from image dimensions — proportional, no stretch."""
    try:
        from PIL import Image

        with Image.open(logo_path) as im:
            w, h = im.size
        if w <= 0 or h <= 0:
            return {"x_scale": 0.45, "y_scale": 0.45, "object_position": 1, "x_offset": 0, "y_offset": 2}
        scale = min(max_width_px / float(w), max_height_px / float(h), 1.0)
        # xlsxwriter: 1.0 ≈ 100% of native bitmap width in default placement
        s = max(0.05, min(scale, 1.0))
        return {
            "x_scale": s,
            "y_scale": s,
            "object_position": 1,
            "x_offset": 0,
            "y_offset": 4,
        }
    except Exception:
        return {"x_scale": 0.45, "y_scale": 0.45, "object_position": 1, "x_offset": 0, "y_offset": 2}


def _auto_column_widths(df: pd.DataFrame, header_row_strings: Sequence[str]) -> list[float]:
    """Heuristic Excel column widths (character units)."""
    widths: list[float] = []
    for i, col in enumerate(TABLE_COLUMNS):
        label = header_row_strings[i] if i < len(header_row_strings) else col
        m = len(label)
        if not df.empty and col in df.columns:
            for v in df[col].head(800):
                m = max(m, len(str(v)))
        widths.append(float(min(48, max(9, m + 2))))
    return widths


def write_general_ledger_excel(
    df: pd.DataFrame,
    output: str | Path | BinaryIO,
    *,
    organization_name: str,
    header: GeneralLedgerHeaderContext,
    logo_path: str | None = None,
) -> None:
    if isinstance(output, (str, Path)):
        wb = xlsxwriter.Workbook(str(output))
    else:
        output.seek(0)
        output.truncate(0)
        wb = xlsxwriter.Workbook(output, {"in_memory": True})

    ws = wb.add_worksheet("General Ledger")
    ws.set_landscape()
    ws.set_paper(9)
    ws.fit_to_pages(1, 0)
    ws.set_margins(left=0.4, right=0.4, top=0.45, bottom=0.45)

    num_cols = len(TABLE_COLUMNS)
    last_col = num_cols - 1

    border_thin = {"border": 1, "border_color": "#B4B4B4"}
    fmt_org = wb.add_format({"bold": True, "font_size": 14, "align": "center", "valign": "vcenter"})
    fmt_logo_row = wb.add_format({"align": "center", "valign": "vcenter"})
    fmt_head_line = wb.add_format({"bold": True, "align": "center", "valign": "vcenter"})
    fmt_head_plain = wb.add_format({"align": "center", "valign": "vcenter"})
    fmt_spacer = wb.add_format({})

    fmt_hdr_left = wb.add_format(
        {
            "bold": True,
            "bottom": 2,
            "border": 1,
            "border_color": "#B4B4B4",
            "text_wrap": True,
            "valign": "vcenter",
            "align": "left",
        }
    )
    fmt_hdr_right = wb.add_format(
        {
            "bold": True,
            "bottom": 2,
            "border": 1,
            "border_color": "#B4B4B4",
            "text_wrap": True,
            "valign": "vcenter",
            "align": "right",
        }
    )
    fmt_cell_left = wb.add_format({"border": 1, "border_color": "#B4B4B4", "valign": "top", "align": "left"})
    fmt_cell_right = wb.add_format(
        {
            "border": 1,
            "border_color": "#B4B4B4",
            "valign": "top",
            "align": "right",
            "num_format": "#,##0.00",
        }
    )
    fmt_date = wb.add_format(
        {
            "border": 1,
            "border_color": "#B4B4B4",
            "num_format": "yyyy-mm-dd",
            "valign": "top",
            "align": "left",
        }
    )
    fmt_section = wb.add_format(
        {
            "bold": True,
            "align": "center",
            "valign": "vcenter",
            "bg_color": "#E8EEF5",
            **border_thin,
        }
    )
    fmt_budget_section = wb.add_format(
        {
            "italic": True,
            "align": "center",
            "valign": "vcenter",
            "bg_color": "#F5F7FA",
            **border_thin,
        }
    )
    fmt_sub_lbl = wb.add_format(
        {"bold": True, "bg_color": "#EDEDED", "align": "left", "valign": "vcenter", **border_thin}
    )
    fmt_sub_num = wb.add_format(
        {
            "bold": True,
            "bg_color": "#EDEDED",
            "align": "right",
            "valign": "vcenter",
            "num_format": "#,##0.00",
            **border_thin,
        }
    )
    fmt_grand_lbl = wb.add_format({"bold": True, "align": "left", "valign": "vcenter", **border_thin})
    fmt_grand_num = wb.add_format(
        {"bold": True, "align": "right", "valign": "vcenter", "num_format": "#,##0.00", **border_thin}
    )

    row = 0
    org = (organization_name or "").strip() or "Organization"
    ws.merge_range(row, 0, row, last_col, org, fmt_org)
    row += 1

    logo_row = row
    ws.merge_range(row, 0, row, last_col, "", fmt_logo_row)
    ws.set_row(logo_row, 78)
    if logo_path and Path(logo_path).is_file():
        try:
            mid_col = max(0, last_col // 2)
            opts = _logo_insert_options(logo_path)
            ws.insert_image(logo_row, mid_col, logo_path, opts)
        except Exception:
            pass
    row += 1

    ws.merge_range(row, 0, row, last_col, "General Ledger", fmt_head_line)
    row += 1

    ws.merge_range(row, 0, row, last_col, f"Project title: {header.project_title}", fmt_head_plain)
    row += 1
    ws.merge_range(row, 0, row, last_col, f"Donor: {header.donor_name}", fmt_head_plain)
    row += 1
    ws.merge_range(
        row,
        0,
        row,
        last_col,
        f"Period: {header.period_start:%Y-%m-%d} - {header.period_end:%Y-%m-%d}",
        fmt_head_plain,
    )
    row += 1
    ws.merge_range(
        row,
        0,
        row,
        last_col,
        f"Generated date: {header.generated_at:%Y-%m-%d %H:%M}",
        fmt_head_plain,
    )
    row += 1
    ws.merge_range(row, 0, row, last_col, f"Currency: {header.currency_label}", fmt_head_plain)
    row += 1

    ws.set_row(row, 6)
    row += 1

    header_row = row
    for c, name in enumerate(TABLE_COLUMNS):
        f = fmt_hdr_left if name in TEXT_HEADER_COLS else fmt_hdr_right
        ws.write(header_row, c, name, f)
    row += 1

    widths = _auto_column_widths(df, list(TABLE_COLUMNS))
    for c, w in enumerate(widths):
        ws.set_column(c, c, w)

    debit_col = TABLE_COLUMNS.index("Debit")
    credit_col = TABLE_COLUMNS.index("Credit")
    run_col = TABLE_COLUMNS.index("Running balance")

    total_debit = Decimal("0")
    total_credit = Decimal("0")

    if df.empty:
        ws.merge_range(row, 0, row, last_col, "No posted activity for the selected filters.", fmt_cell_left)
        row += 1
    else:
        first_grant = True
        for (_gs, gdf) in df.groupby("_grant_sort", sort=True):
            if not first_grant:
                ws.set_row(row, 6)
                row += 1
            first_grant = False

            grant_label = gdf["_grant_label"].iloc[0]
            ws.merge_range(row, 0, row, last_col, f"Grant: {grant_label}", fmt_section)
            row += 1

            grant_d = Decimal("0")
            grant_c = Decimal("0")

            for (_bs, bdf) in gdf.groupby("_budget_sort", sort=True):
                bl_heading = bdf["_budget_line_label"].iloc[0]
                ws.merge_range(row, 0, row, last_col, f"Budget line: {bl_heading}", fmt_budget_section)
                row += 1

                for _, rec in bdf.iterrows():
                    for c, name in enumerate(TABLE_COLUMNS):
                        val = rec.get(name, "")
                        if name == "Date":
                            if hasattr(val, "year") and hasattr(val, "month") and hasattr(val, "day"):
                                dt = val if isinstance(val, datetime) else datetime.combine(val, time.min)
                                ws.write_datetime(row, c, dt, fmt_date)
                            else:
                                ws.write(row, c, val, fmt_cell_left)
                        elif name in ("Debit", "Credit", "Running balance"):
                            d = _decimal_or_zero(val)
                            ws.write_number(row, c, float(d), fmt_cell_right)
                        else:
                            ws.write(row, c, val if val is not None else "", fmt_cell_left)
                    row += 1

                grant_d += sum(_decimal_or_zero(x) for x in bdf["Debit"])
                grant_c += sum(_decimal_or_zero(x) for x in bdf["Credit"])

            ws.merge_range(row, 0, row, debit_col - 1, "SUBTOTAL", fmt_sub_lbl)
            ws.write_number(row, debit_col, float(grant_d), fmt_sub_num)
            ws.write_number(row, credit_col, float(grant_c), fmt_sub_num)
            for c in range(credit_col + 1, num_cols):
                ws.write(row, c, "", fmt_sub_lbl)
            row += 1

            total_debit += grant_d
            total_credit += grant_c

    row += 1
    closing = total_debit - total_credit
    ws.merge_range(row, 0, row, debit_col - 1, "GRAND TOTAL", fmt_grand_lbl)
    ws.write_number(row, debit_col, float(total_debit), fmt_grand_num)
    ws.write_number(row, credit_col, float(total_credit), fmt_grand_num)
    ws.write_number(row, run_col, float(closing), fmt_grand_num)
    for c in range(run_col + 1, num_cols):
        ws.write(row, c, "", fmt_grand_lbl)

    ws.freeze_panes(header_row + 1, 0)
    ws.repeat_rows(header_row, header_row)
    wb.close()


def export_general_ledger_xlsx_bytes(
    using: str,
    filters: GeneralLedgerFilters,
    *,
    organization_name: str,
    org_settings=None,
    user=None,
) -> bytes:
    df, _opening = fetch_general_ledger_rows(using, filters, user=user)
    header = build_header_context(filters, using, df, org_settings=org_settings)
    buf = io.BytesIO()
    write_general_ledger_excel(
        df,
        buf,
        organization_name=organization_name,
        header=header,
        logo_path=_pick_logo_path(org_settings),
    )
    return buf.getvalue()


def export_general_ledger_xlsx(
    using: str,
    filters: GeneralLedgerFilters,
    path: str | Path,
    *,
    organization_name: str,
    org_settings=None,
    user=None,
) -> None:
    df, _opening = fetch_general_ledger_rows(using, filters, user=user)
    header = build_header_context(filters, using, df, org_settings=org_settings)
    write_general_ledger_excel(
        df,
        path,
        organization_name=organization_name,
        header=header,
        logo_path=_pick_logo_path(org_settings),
    )
