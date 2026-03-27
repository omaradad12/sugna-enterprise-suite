"""
Document Management workspace (central repository + search + settings).

Validation and tenant policy live in ``tenant_documents.services.validation`` and
``tenant_documents.models.DocumentPolicyConfig`` (per-tenant database). Uploads,
list filters, pagination, storage settings, and journal sync use the same rules.

Standalone module: `active_submenu` is always ``documents``; sidebar order matches URLs:
  documents_dashboard, documents_all, documents_upload, documents_categories,
  documents_linked, documents_templates, documents_expiring, documents_approvals,
  documents_audit_files, documents_storage_settings.
Detail and version-history views use active_item ``dm_all`` / ``dm_versions`` (see templates).
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_http_methods

from rbac.models import user_has_permission
from tenant_portal.decorators import tenant_view
from tenant_documents.models import (
    Document,
    DocumentApproval,
    DocumentAuditEvent,
    DocumentCategory,
    DocumentPolicyConfig,
    DocumentStatus,
    DocumentType,
    DocumentVersion,
    StorageProvider,
    StorageProviderConfig,
)
from tenant_documents.services.validation import (
    compute_sha256_django_file,
    enrich_document_file_hash_and_retention,
    get_policy,
    validate_search_params,
    validate_standalone_library_upload,
    validate_storage_provider_config,
    validate_upload_for_policy,
)


def _db(request: HttpRequest) -> str:
    return request.tenant_db


def _can_view_dm(request: HttpRequest) -> bool:
    user = request.tenant_user
    db = _db(request)
    if user_has_permission(user, "documents:workspace.view", using=db):
        return True
    if user_has_permission(user, "finance:attachments.view", using=db):
        return True
    if user_has_permission(user, "auditor:readonly", using=db):
        return True
    return False


def _can_upload_dm(request: HttpRequest) -> bool:
    user = request.tenant_user
    db = _db(request)
    if user_has_permission(user, "documents:document.upload", using=db):
        return True
    return user_has_permission(user, "finance:attachments.upload", using=db)


def _can_manage_dm(request: HttpRequest) -> bool:
    user = request.tenant_user
    db = _db(request)
    if user_has_permission(user, "documents:document.manage", using=db):
        return True
    return user_has_permission(user, "rbac:roles.manage", using=db)


def _dm_ctx(request: HttpRequest, *, active_item: str, **extra):
    """Layout template (_layout_fullwidth) expects tenant, tenant_user, org_settings (via context processor)."""
    return {
        "tenant": request.tenant,
        "tenant_user": request.tenant_user,
        "tenant_db": getattr(request, "tenant_db", None),
        "active_submenu": "documents",
        "active_item": active_item,
        "dm_can_upload": _can_upload_dm(request),
        "dm_can_manage": _can_manage_dm(request),
        **extra,
    }


def _filter_documents(request: HttpRequest, qs, policy: DocumentPolicyConfig):
    p = validate_search_params(request.GET, policy)
    q = p["q"]
    if q:
        qs = qs.filter(
            Q(original_filename__icontains=q)
            | Q(voucher_number__icontains=q)
            | Q(tags__icontains=q)
            | Q(module__icontains=q)
        )
    if p["module"]:
        qs = qs.filter(module=p["module"])
    if p["status"]:
        qs = qs.filter(status=p["status"])
    if p["category"] is not None:
        qs = qs.filter(category_id=p["category"])
    if p["document_type"]:
        qs = qs.filter(document_type=p["document_type"])
    return qs, p


def _query_no_page(request: HttpRequest) -> str:
    q = request.GET.copy()
    q.pop("page", None)
    return q.urlencode()


def _forbidden(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "tenant_portal/forbidden.html",
        {
            "tenant": request.tenant,
            "tenant_user": request.tenant_user,
            "reason": "You do not have permission to access Document Management.",
        },
        status=403,
    )


def _ensure_document_schema(request: HttpRequest) -> HttpResponse | None:
    """
    Tenant DBs must apply tenant_documents.0002 (DocumentPolicyConfig). When
    TENANT_AUTO_MIGRATE is true, migrate the alias once; otherwise show 503 + instructions.
    """
    from django.conf import settings

    from tenant_portal.migration_checks import ensure_document_policy_schema

    tenant_db = _db(request)
    if ensure_document_policy_schema(tenant_db, auto_migrate=getattr(settings, "TENANT_AUTO_MIGRATE", False)):
        return None
    return render(
        request,
        "tenant_portal/finance/tenant_migration_required.html",
        {
            "tenant": request.tenant,
            "tenant_user": request.tenant_user,
            "tenant_db": tenant_db,
            "migration_label": "tenant_documents.0002_documentpolicyconfig_document_file_sha256_and_more",
            "active_submenu": "documents",
            "active_item": "dm_dashboard",
            "show_account_category_seed": False,
        },
        status=503,
    )


@tenant_view()
@require_http_methods(["GET", "HEAD"])
def documents_dashboard_view(request: HttpRequest) -> HttpResponse:
    if not _can_view_dm(request):
        return _forbidden(request)
    dm_schema = _ensure_document_schema(request)
    if dm_schema:
        return dm_schema
    db = _db(request)
    policy = get_policy(db)
    now = timezone.now()
    horizon = now + timedelta(days=30)
    total = Document.objects.using(db).count()
    recent = list(Document.objects.using(db).select_related("uploaded_by", "category")[:12])
    by_module = (
        Document.objects.using(db)
        .exclude(module="")
        .values("module")
        .annotate(n=Count("id"))
        .order_by("-n")[:12]
    )
    by_category = (
        Document.objects.using(db)
        .exclude(category__isnull=True)
        .values("category__name")
        .annotate(n=Count("id"))
        .order_by("-n")[:12]
    )
    pending_approvals = DocumentApproval.objects.using(db).filter(state=DocumentApproval.State.PENDING).count()
    expiring_soon = Document.objects.using(db).filter(expires_at__isnull=False, expires_at__lte=horizon, expires_at__gte=now).count()
    draft_ct = Document.objects.using(db).filter(status=DocumentStatus.DRAFT).count()
    posted_ct = Document.objects.using(db).filter(status=DocumentStatus.POSTED).count()
    return render(
        request,
        "tenant_portal/documents/dashboard.html",
        _dm_ctx(
            request,
            active_item="dm_dashboard",
            total_documents=total,
            recent_documents=recent,
            by_module=by_module,
            by_category=by_category,
            pending_approvals=pending_approvals,
            expiring_soon=expiring_soon,
            draft_count=draft_ct,
            posted_count=posted_ct,
            dm_policy=policy,
        ),
    )


@tenant_view()
@require_http_methods(["GET", "HEAD"])
def documents_all_view(request: HttpRequest) -> HttpResponse:
    if not _can_view_dm(request):
        return _forbidden(request)
    dm_schema = _ensure_document_schema(request)
    if dm_schema:
        return dm_schema
    db = _db(request)
    policy = get_policy(db)
    qs = Document.objects.using(db).select_related("uploaded_by", "category", "project", "grant", "donor")
    qs, sp = _filter_documents(request, qs, policy)
    qs = qs.order_by("-uploaded_at")
    paginator = Paginator(qs, sp["per_page"])
    page = paginator.get_page(sp["page"])
    categories = DocumentCategory.objects.using(db).order_by("sort_order", "name")
    return render(
        request,
        "tenant_portal/documents/all_documents.html",
        _dm_ctx(
            request,
            active_item="dm_all",
            page_obj=page,
            categories=categories,
            status_choices=DocumentStatus.choices,
            document_type_choices=DocumentType.choices,
            query_no_page=_query_no_page(request),
            dm_policy=policy,
        ),
    )


@tenant_view()
@require_http_methods(["GET", "HEAD", "POST"])
def documents_upload_view(request: HttpRequest) -> HttpResponse:
    if not _can_view_dm(request):
        return _forbidden(request)
    dm_schema = _ensure_document_schema(request)
    if dm_schema:
        return dm_schema
    if not _can_upload_dm(request):
        return _forbidden(request)
    db = _db(request)
    policy = get_policy(db)
    categories = DocumentCategory.objects.using(db).order_by("sort_order", "name")
    if request.method == "POST":
        f = request.FILES.get("file")
        if not f:
            messages.error(request, "Choose a file to upload.")
        else:
            try:
                f.seek(0)
                validate_upload_for_policy(f, policy)
                f.seek(0)
                sha = compute_sha256_django_file(f)
                f.seek(0)
                doc = Document(
                    file=f,
                    original_filename=getattr(f, "name", "") or "",
                    document_type=(request.POST.get("document_type") or DocumentType.OTHER).strip(),
                    tags=(request.POST.get("tags") or "").strip(),
                    module=(request.POST.get("module") or "document_management").strip(),
                    submodule=(request.POST.get("submodule") or "library").strip(),
                    linked_record_type="standalone",
                    tenant_key=db,
                    uploaded_by=request.tenant_user,
                    status=DocumentStatus.DRAFT,
                    storage_provider="LocalDjangoMediaBackend",
                    file_sha256=sha,
                )
                cid = request.POST.get("category")
                if cid:
                    doc.category_id = int(cid)
                doc.refresh_file_metadata()
                validate_standalone_library_upload(doc=doc, policy=policy, using=db)
                doc.save(using=db)
                enrich_document_file_hash_and_retention(doc, db, policy)
                doc.save(
                    using=db,
                    update_fields=["file_sha256", "size_bytes", "mime_type", "retention_until"],
                )
                DocumentAuditEvent.objects.using(db).create(
                    document=doc,
                    action=DocumentAuditEvent.Action.CREATED,
                    message="Library upload validated per tenant document policy",
                    actor=request.tenant_user,
                    payload={"max_file_size_bytes": policy.max_file_size_bytes},
                )
                messages.success(request, "Document registered.")
                return redirect(reverse("tenant_portal:documents_detail", kwargs={"doc_id": doc.pk}))
            except ValidationError as e:
                for msg in e.messages:
                    messages.error(request, msg)
    return render(
        request,
        "tenant_portal/documents/upload.html",
        _dm_ctx(
            request,
            active_item="dm_upload",
            categories=categories,
            document_type_choices=DocumentType.choices,
            dm_policy=policy,
        ),
    )


@tenant_view()
@require_http_methods(["GET", "HEAD", "POST"])
def documents_categories_view(request: HttpRequest) -> HttpResponse:
    if not _can_view_dm(request):
        return _forbidden(request)
    dm_schema = _ensure_document_schema(request)
    if dm_schema:
        return dm_schema
    db = _db(request)
    if request.method == "POST":
        if not _can_manage_dm(request):
            return _forbidden(request)
        name = (request.POST.get("name") or "").strip()
        if name:
            base_slug = slugify(name)[:140] or "category"
            slug = base_slug
            n = 1
            while DocumentCategory.objects.using(db).filter(slug=slug).exists():
                slug = f"{base_slug}-{n}"
                n += 1
            DocumentCategory.objects.using(db).create(
                name=name,
                slug=slug,
                code=(request.POST.get("code") or "").strip()[:40],
                sort_order=int(request.POST.get("sort_order") or 0),
            )
            messages.success(request, "Category added.")
        return redirect(reverse("tenant_portal:documents_categories"))
    rows = DocumentCategory.objects.using(db).order_by("sort_order", "name")
    return render(request, "tenant_portal/documents/categories.html", _dm_ctx(request, active_item="dm_categories", categories=rows))


@tenant_view()
@require_http_methods(["GET", "HEAD"])
def documents_linked_view(request: HttpRequest) -> HttpResponse:
    if not _can_view_dm(request):
        return _forbidden(request)
    dm_schema = _ensure_document_schema(request)
    if dm_schema:
        return dm_schema
    db = _db(request)
    policy = get_policy(db)
    qs = Document.objects.using(db).exclude(linked_record_type="").exclude(linked_record_type="standalone")
    qs, sp = _filter_documents(request, qs, policy)
    qs = qs.order_by("-uploaded_at")
    paginator = Paginator(qs, sp["per_page"])
    page = paginator.get_page(sp["page"])
    return render(
        request,
        "tenant_portal/documents/linked.html",
        _dm_ctx(
            request,
            active_item="dm_linked",
            page_obj=page,
            query_no_page=_query_no_page(request),
            dm_policy=policy,
        ),
    )


@tenant_view()
@require_http_methods(["GET", "HEAD"])
def documents_expiring_view(request: HttpRequest) -> HttpResponse:
    if not _can_view_dm(request):
        return _forbidden(request)
    dm_schema = _ensure_document_schema(request)
    if dm_schema:
        return dm_schema
    db = _db(request)
    policy = get_policy(db)
    sp = validate_search_params(request.GET, policy)
    now = timezone.now()
    horizon = now + timedelta(days=90)
    qs = Document.objects.using(db).filter(expires_at__isnull=False, expires_at__lte=horizon).order_by("expires_at")
    paginator = Paginator(qs, sp["per_page"])
    page = paginator.get_page(sp["page"])
    return render(
        request,
        "tenant_portal/documents/expiring.html",
        _dm_ctx(
            request,
            active_item="dm_expiring",
            page_obj=page,
            query_no_page=_query_no_page(request),
            dm_policy=policy,
        ),
    )


@tenant_view()
@require_http_methods(["GET", "HEAD", "POST"])
def documents_approvals_view(request: HttpRequest) -> HttpResponse:
    if not _can_view_dm(request):
        return _forbidden(request)
    dm_schema = _ensure_document_schema(request)
    if dm_schema:
        return dm_schema
    db = _db(request)
    qs = (
        DocumentApproval.objects.using(db)
        .filter(state=DocumentApproval.State.PENDING)
        .select_related("document", "assigned_to")
        .order_by("created_at")
    )
    return render(request, "tenant_portal/documents/approvals.html", _dm_ctx(request, active_item="dm_approvals", approvals=qs))


@tenant_view()
@require_http_methods(["GET", "HEAD"])
def documents_audit_files_view(request: HttpRequest) -> HttpResponse:
    if not _can_view_dm(request):
        return _forbidden(request)
    dm_schema = _ensure_document_schema(request)
    if dm_schema:
        return dm_schema
    db = _db(request)
    policy = get_policy(db)
    sp = validate_search_params(request.GET, policy)
    qs = Document.objects.using(db).filter(
        Q(document_type=DocumentType.AUDIT_EVIDENCE) | Q(module__icontains="audit") | Q(tags__icontains="audit")
    ).order_by("-uploaded_at")
    paginator = Paginator(qs, sp["per_page"])
    page = paginator.get_page(sp["page"])
    return render(
        request,
        "tenant_portal/documents/audit_files.html",
        _dm_ctx(
            request,
            active_item="dm_audit",
            page_obj=page,
            query_no_page=_query_no_page(request),
            dm_policy=policy,
        ),
    )


@tenant_view()
@require_http_methods(["GET", "HEAD"])
def documents_templates_view(request: HttpRequest) -> HttpResponse:
    if not _can_view_dm(request):
        return _forbidden(request)
    dm_schema = _ensure_document_schema(request)
    if dm_schema:
        return dm_schema
    db = _db(request)
    policy = get_policy(db)
    sp = validate_search_params(request.GET, policy)
    qs = Document.objects.using(db).filter(document_type=DocumentType.TEMPLATE).order_by("-uploaded_at")
    paginator = Paginator(qs, sp["per_page"])
    page = paginator.get_page(sp["page"])
    return render(
        request,
        "tenant_portal/documents/templates_page.html",
        _dm_ctx(
            request,
            active_item="dm_templates",
            page_obj=page,
            query_no_page=_query_no_page(request),
            dm_policy=policy,
        ),
    )


@tenant_view()
@require_http_methods(["GET", "HEAD", "POST"])
def documents_storage_settings_view(request: HttpRequest) -> HttpResponse:
    if not _can_view_dm(request):
        return _forbidden(request)
    dm_schema = _ensure_document_schema(request)
    if dm_schema:
        return dm_schema
    if not _can_manage_dm(request):
        return _forbidden(request)
    db = _db(request)
    cfg = StorageProviderConfig.get_solo(using=db)
    policy = get_policy(db)
    if request.method == "POST":
        prov = (request.POST.get("provider") or StorageProvider.LOCAL).strip()
        if prov in {c for c, _ in StorageProvider.choices}:
            cfg.provider = prov
            cfg.config_notes = (request.POST.get("config_notes") or "").strip()
            try:
                validate_storage_provider_config(cfg, policy)
                cfg.save(using=db, update_fields=["provider", "config_notes", "updated_at"])
                messages.success(
                    request,
                    "Storage settings saved. (Local storage is active; other providers are prepared for future configuration.)",
                )
            except ValidationError as e:
                for msg in e.messages:
                    messages.error(request, msg)
            else:
                return redirect(reverse("tenant_portal:documents_storage_settings"))
        else:
            messages.error(request, "Invalid storage provider.")
    return render(
        request,
        "tenant_portal/documents/storage_settings.html",
        _dm_ctx(
            request,
            active_item="dm_storage",
            config=cfg,
            provider_choices=StorageProvider.choices,
            dm_policy=policy,
        ),
    )


@tenant_view()
@require_http_methods(["GET", "HEAD"])
def documents_version_history_view(request: HttpRequest, doc_id: int) -> HttpResponse:
    if not _can_view_dm(request):
        return _forbidden(request)
    dm_schema = _ensure_document_schema(request)
    if dm_schema:
        return dm_schema
    db = _db(request)
    doc = get_object_or_404(Document.objects.using(db).select_related("uploaded_by"), pk=doc_id)
    versions = DocumentVersion.objects.using(db).filter(document_id=doc.id).order_by("-version")
    events = DocumentAuditEvent.objects.using(db).filter(document_id=doc.id).select_related("actor").order_by("-created_at")[:200]
    return render(
        request,
        "tenant_portal/documents/version_history.html",
        _dm_ctx(
            request,
            active_item="dm_versions",
            document=doc,
            versions=versions,
            events=events,
            dm_policy=get_policy(db),
        ),
    )


@tenant_view()
@require_http_methods(["GET", "HEAD"])
def documents_detail_view(request: HttpRequest, doc_id: int) -> HttpResponse:
    if not _can_view_dm(request):
        return _forbidden(request)
    dm_schema = _ensure_document_schema(request)
    if dm_schema:
        return dm_schema
    db = _db(request)
    policy = get_policy(db)
    doc = get_object_or_404(
        Document.objects.using(db).select_related("uploaded_by", "category", "project", "grant", "donor", "source_journal_attachment"),
        pk=doc_id,
    )
    events = DocumentAuditEvent.objects.using(db).filter(document_id=doc.id).select_related("actor").order_by("-created_at")[:50]
    return render(
        request,
        "tenant_portal/documents/detail.html",
        _dm_ctx(request, active_item="dm_all", document=doc, events=events, dm_policy=policy),
    )
