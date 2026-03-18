from __future__ import annotations

from dataclasses import dataclass
import string


@dataclass(frozen=True)
class GeneratedNumber:
    value: str
    seq: int
    period_key: str


def _period_key(reset_frequency: str, entry_date) -> str:
    rf = (reset_frequency or "").strip().lower()
    if rf == "monthly":
        return f"{entry_date.year:04d}-{entry_date.month:02d}"
    if rf == "yearly":
        return f"{entry_date.year:04d}"
    return "all"


ALLOWED_TOKENS = {
    "prefix",
    "year",
    "month",
    "seq",
    "project_code",
    "grant_code",
    "fy",
    "fiscal_year",
}


def validate_number_format(fmt: str) -> list[str]:
    """
    Validate python-format template for DocumentSeries.number_format.
    - Only allows known tokens
    - Requires {seq} token
    """
    f = (fmt or "").strip()
    if not f:
        return ["Number format is required."]
    if len(f) > 80:
        return ["Number format is too long (max 80 characters)."]

    errors: list[str] = []
    tokens: set[str] = set()
    try:
        for _, field_name, _, _ in string.Formatter().parse(f):
            if not field_name:
                continue
            # field_name can contain format accessors; we only allow base names
            base = field_name.split(".", 1)[0].split("[", 1)[0]
            tokens.add(base)
    except Exception:
        return ["Number format is invalid. Use tokens like {prefix}{year}-{seq:05d}."]

    unknown = sorted(t for t in tokens if t not in ALLOWED_TOKENS)
    if unknown:
        errors.append(f"Unknown tokens in number format: {', '.join(unknown)}.")
    if "seq" not in tokens:
        errors.append("Number format must include the {seq} token.")

    # Dry-run format
    try:
        f.format(
            prefix="PV-",
            year="2026",
            month="03",
            seq=1,
            project_code="PRJ001",
            grant_code="GRT001",
            fy="FY2026",
            fiscal_year="FY2026",
        )
    except Exception:
        errors.append("Number format is not a valid Python format string.")

    return errors


def preview_number(*, fmt: str, prefix: str, entry_date, seq: int, project_code: str = "", grant_code: str = "", fiscal_year: str = "") -> str:
    f = (fmt or "").strip() or "{prefix}{year}-{seq:05d}"
    context = {
        "prefix": prefix or "",
        "year": f"{entry_date.year:04d}",
        "month": f"{entry_date.month:02d}",
        "seq": int(seq or 1),
        "project_code": project_code or "",
        "grant_code": grant_code or "",
        "fy": fiscal_year or "",
        "fiscal_year": fiscal_year or "",
    }
    return f.format(**context)


def generate_document_number(
    *,
    using: str,
    document_type: str,
    entry_date,
    project=None,
    grant=None,
) -> GeneratedNumber:
    """
    Generate a document number from DocumentSeries with:
    - Fiscal-year preference
    - Scope (global/project/grant)
    - Reset logic (yearly/monthly/never) via DocumentSequenceCounter
    - Safe formatting with a stable context
    """
    from django.db import transaction

    from tenant_finance.models import (
        DocumentSeries,
        DocumentSequenceCounter,
        DocumentNumberLog,
        AuditLog,
        FiscalYear,
    )

    fy = (
        FiscalYear.objects.using(using)
        .filter(start_date__lte=entry_date, end_date__gte=entry_date)
        .order_by("-start_date")
        .first()
    )

    qs = DocumentSeries.objects.using(using).filter(
        document_type=document_type,
        status=DocumentSeries.Status.ACTIVE,
    )

    # Resolve scope targets
    scope = DocumentSeries.Scope.GLOBAL
    scope_project = None
    scope_grant = None
    if grant is not None:
        scope_grant = grant
    if project is not None:
        scope_project = project

    # Prefer the most specific configured series
    candidates = []
    if scope_grant is not None:
        candidates.append((DocumentSeries.Scope.GRANT, None, scope_grant))
    if scope_project is not None:
        candidates.append((DocumentSeries.Scope.PROJECT, scope_project, None))
    candidates.append((DocumentSeries.Scope.GLOBAL, None, None))

    series = None
    for sc, prj, gr in candidates:
        scoped = qs.filter(scope=sc, project=prj, grant=gr)
        if fy:
            series = scoped.filter(fiscal_year=fy).first()
        if not series:
            series = scoped.filter(fiscal_year__isnull=True).first()
        if series:
            scope = sc
            scope_project = prj
            scope_grant = gr
            break

    if not series:
        raise ValueError("No active document series is configured for this document type.")

    pkey = _period_key(series.reset_frequency, entry_date)

    with transaction.atomic(using=using):
        counter, _ = (
            DocumentSequenceCounter.objects.using(using)
            .select_for_update()
            .get_or_create(
                series=series,
                period_key=pkey,
                project=scope_project if scope == DocumentSeries.Scope.PROJECT else None,
                grant=scope_grant if scope == DocumentSeries.Scope.GRANT else None,
                defaults={"current_number": 0},
            )
        )

        base = series.start_number - 1 if (series.start_number or 1) > 0 else 0
        current = max(counter.current_number, base) + 1
        counter.current_number = current
        counter.save(using=using, update_fields=["current_number"])

        # Keep series current_number as a convenience indicator (max seen so far)
        if current > (series.current_number or 0):
            series.current_number = current
            series.save(using=using, update_fields=["current_number"])

        fiscal_year_token = getattr(fy, "name", "") if fy else ""
        context = {
            "prefix": series.prefix,
            "year": f"{entry_date.year:04d}",
            "month": f"{entry_date.month:02d}",
            "seq": current,
            "project_code": getattr(scope_project, "code", "") if scope_project else "",
            "grant_code": getattr(scope_grant, "code", "") if scope_grant else "",
            "fy": fiscal_year_token,
            "fiscal_year": fiscal_year_token,
        }
        fmt = series.number_format or "{prefix}{year}-{seq:05d}"
        fmt_errors = validate_number_format(fmt)
        if fmt_errors:
            raise ValueError("; ".join(fmt_errors))
        try:
            value = fmt.format(**context)
        except Exception:
            value = f"{series.prefix}{entry_date.year}-{current:05d}"

        # Enforce uniqueness of generated value across the tenant
        if DocumentNumberLog.objects.using(using).filter(value=value).exists():
            raise ValueError("Generated document number already exists. Review series format and scope.")

        DocumentNumberLog.objects.using(using).create(
            series=series,
            value=value,
            seq=current,
            period_key=pkey,
            document_type=document_type,
            scope=scope,
            project=scope_project if scope == DocumentSeries.Scope.PROJECT else None,
            grant=scope_grant if scope == DocumentSeries.Scope.GRANT else None,
        )
        AuditLog.objects.using(using).create(
            model_name="documentnumber",
            object_id=series.id,
            action=AuditLog.Action.CREATE,
            user_id=None,
            username="",
            summary=f"Generated number {value} for {document_type}.",
            new_data={
                "value": value,
                "series_id": series.id,
                "seq": current,
                "period_key": pkey,
                "scope": scope,
                "project_id": getattr(scope_project, "id", None),
                "grant_id": getattr(scope_grant, "id", None),
                "fiscal_year": fiscal_year_token,
            },
        )

    return GeneratedNumber(value=value, seq=current, period_key=pkey)

