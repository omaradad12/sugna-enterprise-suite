from __future__ import annotations

from typing import Dict, List

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from tenant_portal.decorators import tenant_view
from tenant_finance.models import AuditLog
from tenant_users.models import TenantUser
from rbac.models import Permission, Role, RolePermission, UserRole


def _actor_name(request: HttpRequest) -> str:
    u = getattr(request, "tenant_user", None)
    if not u:
        return ""
    return (getattr(u, "full_name", "") or "").strip() or getattr(u, "email", "") or ""


def _is_tenant_permission_code(code: str) -> bool:
    """
    Tenant-level RBAC only.

    Excludes platform/tenant provisioning and module entitlement management.
    """
    c = (code or "").strip()
    if not c:
        return False
    if c.startswith("platform:"):
        return False
    # Module entitlement management is a platform concern, not tenant RBAC
    if c == "module:modules.manage":
        return False
    return c.startswith(
        (
            "module:",
            "users:",
            "rbac:",
            # Finance + transactional modules
            "finance:",
            "cashbook:",
            "cashbank:",
            "core_accounting:",
            "funds_donors:",
            "budgeting:",
            "incoming_fund:",
            "outgoing_fund:",
            "cost_sharing:",
            "governance:",
            "reporting:",
            "setup:",
            # Cross-cutting
            "dashboard:",
            "notifications:",
            "alerts:",
            "api:",
            "auditor:",
            # Existing module namespaces
            "grants:",
            "integrations:",
            "audit_risk:",
        )
    )


def _group_permissions(perms: List[Permission]) -> Dict[str, List[Permission]]:
    """
    Group permissions by a logical prefix (e.g. module or area) for display.
    """
    grouped: Dict[str, List[Permission]] = {}
    for p in perms:
        prefix = p.code.split(":", 1)[0]
        if prefix.startswith("module"):
            prefix = p.code.split(":", 2)[1] if ":" in p.code else prefix
        grouped.setdefault(prefix, []).append(p)
    return grouped


_MATRIX_ACTIONS = [
    "view",
    "create",
    "edit",
    "delete",
    "approve",
    "post",
    "reverse",
]


_ENTERPRISE_TABS = [
    {"key": "financial", "title": "Financial"},
    {"key": "procurement", "title": "Procurement"},
    {"key": "hr", "title": "HR"},
    {"key": "approvals", "title": "Approvals"},
    {"key": "system", "title": "System"},
]


def _role_templates() -> list[dict]:
    """
    Enterprise role templates (client-side convenience; server still validates allowed permissions).
    Codes must exist in tenant Permission table to be selectable.
    """
    return [
        {
            "key": "finance_manager",
            "name": "Finance Manager",
            "role_type": Role.RoleType.FINANCIAL,
            "description": "Full financial control + approvals (Maker–Checker).",
            "permission_codes": [
                "module:finance.view",
                "module:finance.manage",
                "finance:scope.all_grants",
                "finance:scope.all_cost_centers",
                "finance:reporting.view",
                "finance:reporting.export",
                "finance:journals.view",
                "finance:journals.create",
                "finance:journals.edit",
                "finance:journals.delete",
                "finance:journals.approve",
                "finance:journals.post",
                "finance:journals.reverse",
                "finance:vouchers.view",
                "finance:vouchers.create",
                "finance:vouchers.edit",
                "finance:vouchers.delete",
                "finance:vouchers.approve",
                "finance:vouchers.post",
                "finance:vouchers.reverse",
                "finance:payments.view",
                "finance:payments.create",
                "finance:payments.approve",
                "finance:payments.post",
                "finance:payments.reverse",
                "cashbank:accounts.view",
                "cashbank:accounts.manage",
                "cashbank:reconciliation.view",
                "cashbank:reconciliation.manage",
                "cashbank:reconciliation.post",
                "cashbook:entries.view",
                "finance:audit.view",
                "dashboard:view",
            ],
        },
        {
            "key": "finance_officer",
            "name": "Finance Officer",
            "role_type": Role.RoleType.FINANCIAL,
            "description": "Create and submit transactions; cannot approve/post.",
            "permission_codes": [
                "module:finance.view",
                "finance:journals.view",
                "finance:journals.create",
                "finance:journals.edit",
                "finance:vouchers.view",
                "finance:vouchers.create",
                "finance:vouchers.edit",
                "finance:payments.view",
                "finance:payments.create",
                "finance:reporting.view",
                "finance:reporting.export",
                "cashbank:accounts.view",
                "cashbook:entries.view",
                "dashboard:view",
            ],
        },
        {
            "key": "cashier",
            "name": "Cashier",
            "role_type": Role.RoleType.OPERATIONAL,
            "description": "Restricted to Cashbook only.",
            "permission_codes": [
                "module:main_cashbook.view",
                "cashbook:entries.view",
            ],
        },
        {
            "key": "tenant_admin",
            "name": "Admin (User Management)",
            "role_type": Role.RoleType.ADMIN,
            "description": "Manage users/roles; read-only finance visibility.",
            "permission_codes": [
                "users:manage",
                "rbac:roles.manage",
                "module:finance.view",
                "finance:journals.view",
                "finance:vouchers.view",
                "finance:payments.view",
                "finance:reporting.view",
                "finance:reporting.export",
                "finance:audit.view",
                "dashboard:view",
            ],
        },
    ]


def _tab_for_module_title(title: str) -> str:
    t = (title or "").strip().lower()
    # Financial (includes internal control / former governance namespace)
    if t in {
        "finance",
        "cashbank",
        "cashbook",
        "core accounting",
        "incoming fund",
        "outgoing fund",
        "funds donors",
        "budgeting",
        "reporting",
        "receivables",
        "payables",
        "reports",
        "multi donor sharing",
        "cost allocation",
        "cost sharing",
        "governance",
        "internal control",
    }:
        return "financial"
    # Procurement (in this suite, procurement lives under grants/procurement flows)
    if t in {"grants", "procurement"}:
        return "procurement"
    # System / access control
    if t in {"users", "rbac", "dashboard", "notifications", "alerts", "api", "integrations", "auditor"}:
        return "system"
    return "financial"


def _section_for_module_title(title: str) -> str:
    t = (title or "").strip().lower()
    if t in {"cashbank", "cashbook"}:
        return "Cash & Bank"
    if t in {"core accounting", "finance"}:
        return "Core Accounting"
    if t in {"incoming fund", "receivables"}:
        return "Receivables"
    if t in {"outgoing fund", "payables"}:
        return "Payables"
    if t in {"funds donors"}:
        return "Funds & Donors"
    if t in {"budgeting"}:
        return "Budgeting"
    if t in {"reporting", "reports"}:
        return "Reports"
    if t in {"multi donor sharing", "cost allocation", "cost sharing"}:
        return "Cost Allocation"
    if t in {"grants"}:
        return "Procurement & Grants"
    if t in {"governance", "internal control"}:
        return "Internal Control"
    if t in {"users", "rbac"}:
        return "Security"
    return _titleize(title) or "General"


def _permission_risk(action: str, code: str) -> str:
    a = (action or "").strip().lower()
    c = (code or "").strip().lower()
    if a in {"delete", "approve", "post", "reverse"}:
        return "high"
    if "override" in c or "unlock" in c or "backdated" in c:
        return "high"
    return "normal"


def _build_enterprise_catalog(perms: List[Permission]) -> dict:
    """
    Convert the matrix into enterprise UI groups:
      tabs -> sections -> cards (resource) with standard action toggles.
    """
    matrix = _build_permission_matrix(perms)
    tabs: dict[str, dict] = {t["key"]: {"key": t["key"], "title": t["title"], "sections": {}} for t in _ENTERPRISE_TABS}

    for mod in matrix["modules"]:
        tab_key = _tab_for_module_title(mod["title"])
        section_title = _section_for_module_title(mod["title"])
        sec = tabs[tab_key]["sections"].setdefault(section_title, {"title": section_title, "modules": []})
        # Each module becomes a collapsible module group in the section
        sec["modules"].append(
            {
                "key": mod["key"],
                "title": mod["title"],
                "cards": [
                    {
                        "title": row["resource"],
                        "actions": [
                            {
                                "key": a,
                                "label": _titleize(a),
                                "perm": row["cells"].get(a),
                                "risk": _permission_risk(a, (row["cells"].get(a).code if row["cells"].get(a) else "")),
                                "indicator": "approval_required" if a in {"create", "edit"} else ("approval_action" if a in {"approve", "post", "reverse"} else "standard"),
                            }
                            for a in ("view", "create", "edit", "approve", "post", "reverse", "delete")
                            if row["cells"].get(a) is not None
                        ],
                        "other": [
                            {
                                "perm": op,
                                "risk": _permission_risk("other", op.code),
                            }
                            for op in (row.get("other") or [])
                        ],
                        "search_text": f'{mod["title"]} {row["resource"]}',
                    }
                    for row in mod["rows"]
                ],
            }
        )

    # Convert sections dict to lists and sort.
    out_tabs = []
    for t in _ENTERPRISE_TABS:
        tab = tabs[t["key"]]
        sections = list(tab["sections"].values())
        for s in sections:
            s["modules"] = sorted(s["modules"], key=lambda x: (x["title"] or "").lower())
        tab["sections_list"] = sorted(sections, key=lambda x: (x["title"] or "").lower())
        out_tabs.append(tab)

    return {"tabs": out_tabs}


def _titleize(s: str) -> str:
    v = (s or "").strip().replace("_", " ").replace("-", " ")
    return " ".join([w[:1].upper() + w[1:] for w in v.split() if w])


def _matrix_module_display_title(raw: str) -> str:
    """Map legacy permission namespace labels to current product names in the security matrix."""
    t = (raw or "").strip().lower()
    return {
        "incoming fund": "Receivables",
        "outgoing fund": "Payables",
        "reporting": "Reports",
        "governance": "Internal Control",
        "multi donor sharing": "Cost Allocation",
        "cost sharing": "Cost Allocation",
    }.get(t, raw)


def _matrix_resource_display_title(raw: str) -> str:
    """Same mapping for matrix resources (e.g. module entitlements under Module access)."""
    t = (raw or "").strip().lower()
    return {
        "incoming fund": "Receivables",
        "outgoing fund": "Payables",
        "multi donor sharing": "Cost Allocation",
        "governance": "Internal Control",
        "reporting": "Reports",
    }.get(t, raw)


def _parse_perm(code: str) -> tuple[str, str, str]:
    """
    Convert permission codes into (module, resource, action) for matrix display.

    Examples:
    - finance:journals.post -> ("Finance", "Journals", "post")
    - cashbank:reconciliation.post -> ("Cashbank", "Reconciliation", "post")
    - reporting:export -> ("Reporting", "General", "export")  (non-matrix; UI section: Reports)
    - module:cash_bank.manage -> ("Module", "Cash Bank", "manage") (non-matrix action)
    """
    c = (code or "").strip()
    if ":" not in c:
        return ("Other", _titleize(c) or "General", "")
    ns, rest = c.split(":", 1)
    rest = rest.strip()
    if "." in rest:
        resource, action = rest.rsplit(".", 1)
    else:
        resource, action = "general", rest
    # Keep module-level entitlements out of the action matrix to avoid duplication/confusion.
    # Example: module:cash_bank.view is not the same as cashbank:reconciliation.view.
    # Show it under "Other controls" instead.
    if (ns or "").strip().lower() == "module":
        module = "Module access"
        resource = _titleize(resource) if resource else "General"
        action = f"module_{(action or '').strip().lower()}" if action else "module"
        return (module, resource, action)

    module = _titleize(ns)
    resource = _titleize(resource) if resource else "General"
    action = (action or "").strip().lower()
    return (module or "Other", resource or "General", action)


def _build_permission_matrix(perms: List[Permission]):
    """
    Build a Microsoft Dynamics-style security matrix structure.
    Returns:
      - modules: [{key, title, rows: [{resource, cells: {action: perm|None}, other: [perm...] }]}]
      - other_actions: set[str]
    """
    modules: Dict[str, Dict[str, Dict[str, Permission | None]]] = {}
    other: Dict[str, Dict[str, List[Permission]]] = {}
    other_actions: set[str] = set()

    for p in perms:
        mod, res, act = _parse_perm(p.code)
        if act in _MATRIX_ACTIONS:
            modules.setdefault(mod, {}).setdefault(res, {a: None for a in _MATRIX_ACTIONS})
            modules[mod][res][act] = p
        else:
            other_actions.add(act or "other")
            other.setdefault(mod, {}).setdefault(res, []).append(p)

    out_modules = []
    for mod in sorted(set(list(modules.keys()) + list(other.keys()))):
        rows = []
        resources = sorted(set(list(modules.get(mod, {}).keys()) + list(other.get(mod, {}).keys())))
        for res in resources:
            cells = {a: None for a in _MATRIX_ACTIONS}
            if mod in modules and res in modules[mod]:
                cells.update(modules[mod][res])
            # De-duplicate "other controls" by permission code (stable + readable)
            other_list = other.get(mod, {}).get(res, [])
            dedup = {}
            for op in other_list:
                dedup[getattr(op, "code", str(op))] = op
            rows.append(
                {
                    "resource": _matrix_resource_display_title(res),
                    "cells": cells,
                    "cells_pairs": [{"action": a, "perm": cells.get(a)} for a in _MATRIX_ACTIONS],
                    "other": sorted(dedup.values(), key=lambda x: x.code),
                }
            )
        out_modules.append(
            {
                "key": mod.lower().replace(" ", "_"),
                "title": _matrix_module_display_title(mod),
                "rows": rows,
            }
        )

    return {"modules": out_modules, "matrix_actions": _MATRIX_ACTIONS, "other_actions": sorted(other_actions)}


@tenant_view(require_perm="rbac:roles.manage")
def roles_permissions_list_view(request: HttpRequest) -> HttpResponse:
    """
    View: list all roles configured for the current tenant with counts.
    """
    tenant_db = request.tenant_db
    role_type = (request.GET.get("type") or "").strip()
    roles_qs = Role.objects.using(tenant_db).order_by("name").all()
    if role_type in {Role.RoleType.FINANCIAL, Role.RoleType.OPERATIONAL, Role.RoleType.ADMIN}:
        roles_qs = roles_qs.filter(role_type=role_type)
    roles = list(roles_qs)
    rows = []
    for r in roles:
        perm_count = (
            RolePermission.objects.using(tenant_db)
            .filter(role=r)
            .count()
        )
        user_count = (
            UserRole.objects.using(tenant_db)
            .filter(role=r)
            .count()
        )
        rows.append(
            {
                "role": r,
                "perm_count": perm_count,
                "user_count": user_count,
            }
        )
    return render(
        request,
        "tenant_portal/roles_permissions_list.html",
        {
            "tenant": request.tenant,
            "tenant_user": request.tenant_user,
            "active_submenu": "setup",
            "active_item": "setup_roles_permissions",
            "rows": rows,
            "role_type_filter": role_type,
            "role_type_choices": Role.RoleType.choices,
        },
    )


@tenant_view(require_perm="rbac:roles.manage")
def roles_permissions_add_view(request: HttpRequest) -> HttpResponse:
    """
    Configure: create a new role and assign permissions.
    """
    tenant_db = request.tenant_db
    all_perms = list(
        Permission.objects.using(tenant_db)
        .order_by("code")
        .all()
    )
    allowed_perms = [p for p in all_perms if _is_tenant_permission_code(p.code)]
    allowed_perm_ids = {p.id for p in allowed_perms}
    catalog = _build_enterprise_catalog(allowed_perms)
    templates = _role_templates()
    # Map template permission codes -> existing Permission ids in this tenant DB
    by_code = {p.code: p.id for p in allowed_perms}
    for t in templates:
        t["permission_ids"] = [by_code[c] for c in t.get("permission_codes", []) if c in by_code]

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        description = (request.POST.get("description") or "").strip()
        role_type = (request.POST.get("role_type") or "").strip() or Role.RoleType.OPERATIONAL
        if role_type not in {Role.RoleType.FINANCIAL, Role.RoleType.OPERATIONAL, Role.RoleType.ADMIN}:
            role_type = Role.RoleType.OPERATIONAL
        selected_perm_ids = [
            int(p)
            for p in request.POST.getlist("permissions")
            if p.isdigit() and int(p) in allowed_perm_ids
        ]

        if not name:
            messages.error(request, "Role name is required.")
        elif Role.objects.using(tenant_db).filter(name__iexact=name).exists():
            messages.error(request, "A role with this name already exists.")
        else:
            role = Role.objects.using(tenant_db).create(name=name, description=description, role_type=role_type)
            for pid in selected_perm_ids:
                try:
                    perm = Permission.objects.using(tenant_db).get(pk=pid)
                    RolePermission.objects.using(tenant_db).get_or_create(role=role, permission=perm)
                except Permission.DoesNotExist:
                    continue

            # Audit log: role created
            AuditLog.objects.using(tenant_db).create(
                model_name="rbac.role",
                object_id=role.id,
                action=AuditLog.Action.CREATE,
                user_id=request.tenant_user.id if request.tenant_user else None,
                username=_actor_name(request),
                summary=f"Role created: {role.name}.",
                new_data={
                    "name": role.name,
                    "description": role.description,
                    "role_type": role.role_type,
                    "permissions": selected_perm_ids,
                },
            )
            messages.success(request, f"Role {role.name} has been created.")
            return redirect(reverse("tenant_portal:roles_permissions_list"))

    return render(
        request,
        "tenant_portal/roles_permissions_form.html",
        {
            "tenant": request.tenant,
            "tenant_user": request.tenant_user,
            "active_submenu": "setup",
            "active_item": "setup_roles_permissions",
            "role": None,
            "catalog": catalog,
            "templates": templates,
            "role_type_choices": Role.RoleType.choices,
            "selected_permission_ids": [],
            "is_add": True,
        },
    )


@tenant_view(require_perm="rbac:roles.manage")
def roles_permissions_edit_view(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Configure: edit an existing role and its permission set.
    """
    tenant_db = request.tenant_db
    role = get_object_or_404(Role.objects.using(tenant_db), pk=pk)
    all_perms = list(Permission.objects.using(tenant_db).order_by("code").all())
    allowed_perms = [p for p in all_perms if _is_tenant_permission_code(p.code)]
    allowed_perm_ids = {p.id for p in allowed_perms}
    catalog = _build_enterprise_catalog(allowed_perms)
    existing_perm_ids = list(
        RolePermission.objects.using(tenant_db)
        .filter(role=role)
        .values_list("permission_id", flat=True)
    )
    existing_perm_ids = [pid for pid in existing_perm_ids if pid in allowed_perm_ids]

    if request.method == "POST":
        if getattr(role, "is_system", False):
            messages.error(request, "This is a protected system role and cannot be modified.")
            return redirect(reverse("tenant_portal:roles_permissions_list"))

        old_data = {
            "name": role.name,
            "description": role.description,
            "role_type": getattr(role, "role_type", ""),
            "permissions": existing_perm_ids,
        }
        name = (request.POST.get("name") or "").strip()
        description = (request.POST.get("description") or "").strip()
        role_type = (request.POST.get("role_type") or "").strip() or getattr(role, "role_type", "") or Role.RoleType.OPERATIONAL
        if role_type not in {Role.RoleType.FINANCIAL, Role.RoleType.OPERATIONAL, Role.RoleType.ADMIN}:
            role_type = getattr(role, "role_type", "") or Role.RoleType.OPERATIONAL
        selected_perm_ids = [
            int(p)
            for p in request.POST.getlist("permissions")
            if p.isdigit() and int(p) in allowed_perm_ids
        ]

        if not name:
            messages.error(request, "Role name is required.")
        elif (
            Role.objects.using(tenant_db)
            .filter(name__iexact=name)
            .exclude(pk=role.pk)
            .exists()
        ):
            messages.error(request, "Another role with this name already exists.")
        else:
            role.name = name
            role.description = description
            role.role_type = role_type
            role.save(using=tenant_db, update_fields=["name", "description", "role_type"])

            RolePermission.objects.using(tenant_db).filter(role=role).delete()
            for pid in selected_perm_ids:
                try:
                    perm = Permission.objects.using(tenant_db).get(pk=pid)
                    RolePermission.objects.using(tenant_db).create(role=role, permission=perm)
                except Permission.DoesNotExist:
                    continue

            # Audit log: role updated
            AuditLog.objects.using(tenant_db).create(
                model_name="rbac.role",
                object_id=role.id,
                action=AuditLog.Action.UPDATE,
                user_id=request.tenant_user.id if request.tenant_user else None,
                username=_actor_name(request),
                summary=f"Role updated: {role.name}.",
                old_data=old_data,
                new_data={
                    "name": role.name,
                    "description": role.description,
                    "role_type": getattr(role, "role_type", ""),
                    "permissions": selected_perm_ids,
                },
            )
            messages.success(request, f"Role {role.name} has been updated.")
            return redirect(reverse("tenant_portal:roles_permissions_list"))

    return render(
        request,
        "tenant_portal/roles_permissions_form.html",
        {
            "tenant": request.tenant,
            "tenant_user": request.tenant_user,
            "active_submenu": "setup",
            "active_item": "setup_roles_permissions",
            "role": role,
            "catalog": catalog,
            "templates": _role_templates(),
            "role_type_choices": Role.RoleType.choices,
            "selected_permission_ids": existing_perm_ids,
            "is_add": False,
        },
    )


@tenant_view(require_perm="rbac:roles.manage")
def roles_permissions_assign_view(request: HttpRequest) -> HttpResponse:
    """
    Manage: assign one or more roles to users in the current tenant.
    """
    tenant_db = request.tenant_db
    roles = list(Role.objects.using(tenant_db).order_by("name"))
    users = list(TenantUser.objects.using(tenant_db).order_by("email"))

    if request.method == "POST":
        for u in users:
            field_name = f"user_{u.id}_roles"
            selected_ids = []
            for raw in request.POST.getlist(field_name):
                if raw.isdigit():
                    selected_ids.append(int(raw))
            selected_ids = sorted(set(selected_ids))

            prev_ids = list(
                UserRole.objects.using(tenant_db)
                .filter(user=u)
                .values_list("role_id", flat=True)
            )
            prev_ids = sorted(set(prev_ids))

            # Replace mapping (multi-role)
            UserRole.objects.using(tenant_db).filter(user=u).exclude(role_id__in=selected_ids).delete()
            existing = set(
                UserRole.objects.using(tenant_db)
                .filter(user=u, role_id__in=selected_ids)
                .values_list("role_id", flat=True)
            )
            to_add = [rid for rid in selected_ids if rid not in existing]
            if to_add:
                valid_roles = set(Role.objects.using(tenant_db).filter(id__in=to_add).values_list("id", flat=True))
                UserRole.objects.using(tenant_db).bulk_create(
                    [UserRole(user=u, role_id=rid) for rid in to_add if rid in valid_roles],
                    ignore_conflicts=True,
                )

            if prev_ids != selected_ids:
                prev_names = list(Role.objects.using(tenant_db).filter(id__in=prev_ids).values_list("name", flat=True))
                new_names = list(Role.objects.using(tenant_db).filter(id__in=selected_ids).values_list("name", flat=True))
                AuditLog.objects.using(tenant_db).create(
                    model_name="rbac.userrole",
                    object_id=u.id,
                    action=AuditLog.Action.UPDATE,
                    user_id=request.tenant_user.id if request.tenant_user else None,
                    username=_actor_name(request),
                    summary=f"Roles updated for user {u.email}.",
                    old_data={"roles": prev_names},
                    new_data={"roles": new_names},
                )

        messages.success(request, "User role assignments have been updated.")
        return redirect(reverse("tenant_portal:roles_permissions_assign"))

    rows = []
    for u in users:
        current_role_ids = list(
            UserRole.objects.using(tenant_db).filter(user=u).values_list("role_id", flat=True)
        )
        rows.append(
            {
                "user": u,
                "current_role_ids": set(current_role_ids),
            }
        )

    return render(
        request,
        "tenant_portal/roles_permissions_assign.html",
        {
            "tenant": request.tenant,
            "tenant_user": request.tenant_user,
            "active_submenu": "setup",
            "active_item": "setup_roles_permissions",
            "rows": rows,
            "roles": roles,
        },
    )

