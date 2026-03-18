"""
User Management under Account: list, add, edit, view, deactivate, reset password.
Access: users:manage or Tenant Admin. Dynamics-style UI.
"""
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from rbac.models import Role, UserRole
from tenant_portal.decorators import tenant_view
from tenant_users.models import TenantUser
from tenant_finance.models import AuditLog


def _get_role_display(tenant_user, tenant_db: str) -> str:
    roles = list(
        UserRole.objects.using(tenant_db)
        .filter(user_id=tenant_user.id)
        .values_list("role__name", flat=True)
    )
    if getattr(tenant_user, "is_tenant_admin", False):
        roles = ["Tenant Admin"] + [r for r in roles if r != "Tenant Admin"]
    return ", ".join(roles) if roles else ("Tenant Admin" if getattr(tenant_user, "is_tenant_admin", False) else "—")


@tenant_view(require_perm="users:manage")
def user_management_list_view(request: HttpRequest) -> HttpResponse:
    """List all tenant users with role, department, status, last login, actions."""
    tenant_db = request.tenant_db
    users = list(TenantUser.objects.using(tenant_db).order_by("email"))
    rows = []
    for u in users:
        rows.append({
            "user": u,
            "role_display": _get_role_display(u, tenant_db),
        })
    return render(
        request,
        "tenant_portal/user_management_list.html",
        {
            "tenant": request.tenant,
            "tenant_user": request.tenant_user,
            "rows": rows,
        },
    )


@tenant_view(require_perm="users:manage")
def user_management_detail_view(request: HttpRequest, pk: int) -> HttpResponse:
    """View single user (read-only)."""
    tenant_db = request.tenant_db
    user = get_object_or_404(TenantUser.objects.using(tenant_db), pk=pk)
    role_display = _get_role_display(user, tenant_db)
    assigned_grants = []
    if hasattr(user, "assigned_grants") and user.assigned_grants.exists():
        assigned_grants = list(user.assigned_grants.all()[:50])
    return render(
        request,
        "tenant_portal/user_management_detail.html",
        {
            "tenant": request.tenant,
            "tenant_user": request.tenant_user,
            "target_user": user,
            "role_display": role_display,
            "assigned_grants": assigned_grants,
        },
    )


@tenant_view(require_perm="users:manage")
def user_management_add_view(request: HttpRequest) -> HttpResponse:
    """Add new user: full name, email, phone, role, department, status, optional assigned projects."""
    tenant_db = request.tenant_db
    roles = list(Role.objects.using(tenant_db).order_by("name"))
    grants = []
    try:
        from tenant_grants.models import Grant
        grants = list(Grant.objects.using(tenant_db).order_by("code").values_list("id", "code", "title")[:200])
    except Exception:
        pass

    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        full_name = (request.POST.get("full_name") or "").strip()[:200]
        phone_number = (request.POST.get("phone_number") or "").strip()[:30]
        department = (request.POST.get("department") or "").strip()[:120]
        is_active = request.POST.get("status") != "inactive"
        role_id = request.POST.get("role_id")
        password = (request.POST.get("password") or "").strip()
        grant_ids = request.POST.getlist("assigned_grants")

        if not email:
            messages.error(request, "Email is required.")
        elif TenantUser.objects.using(tenant_db).filter(email=email).exists():
            messages.error(request, "A user with this email already exists.")
        elif len(password) < 8:
            messages.error(request, "Password must be at least 8 characters.")
        else:
            user = TenantUser.objects.using(tenant_db).create(
                email=email,
                full_name=full_name,
                phone_number=phone_number,
                department=department,
                is_active=is_active,
            )
            user.set_password(password)
            user.save(update_fields=["password_hash"])
            if role_id:
                try:
                    role = Role.objects.using(tenant_db).get(pk=int(role_id))
                    UserRole.objects.using(tenant_db).get_or_create(user=user, role=role)
                except (ValueError, Role.DoesNotExist):
                    pass
            if hasattr(TenantUser, "assigned_grants") and grant_ids:
                try:
                    from tenant_grants.models import Grant
                    for gid in grant_ids:
                        try:
                            g = Grant.objects.using(tenant_db).get(pk=int(gid))
                            user.assigned_grants.add(g)
                        except (ValueError, Grant.DoesNotExist):
                            pass
                except Exception:
                    pass
            # Audit log: user creation
            AuditLog.objects.using(tenant_db).create(
                model_name="tenantuser",
                object_id=user.id,
                action=AuditLog.Action.CREATE,
                user_id=request.tenant_user.id if request.tenant_user else None,
                username=request.tenant_user.get_full_name() if getattr(request, "tenant_user", None) else "",
                summary=f"User created: {user.email} (role: {role.name if role_id else 'N/A'}).",
                new_data={
                    "email": user.email,
                    "full_name": user.full_name,
                    "department": user.department,
                    "is_active": user.is_active,
                    "assigned_grants": list(getattr(user, 'assigned_grants', []).values_list('id', flat=True))
                    if hasattr(user, 'assigned_grants') else [],
                },
            )
            messages.success(request, f"User {email} has been added.")
            return redirect(reverse("tenant_portal:user_management"))

    return render(
        request,
        "tenant_portal/user_management_form.html",
        {
            "tenant": request.tenant,
            "tenant_user": request.tenant_user,
            "target_user": None,
            "roles": roles,
            "grants": grants,
            "selected_grant_ids": [],
            "current_role_id": None,
            "is_add": True,
        },
    )


@tenant_view(require_perm="users:manage")
def user_management_edit_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Edit user: full name, phone, role, department, assigned projects, status."""
    tenant_db = request.tenant_db
    user = get_object_or_404(TenantUser.objects.using(tenant_db), pk=pk)
    roles = list(Role.objects.using(tenant_db).order_by("name"))
    grants = []
    selected_grant_ids = []
    try:
        from tenant_grants.models import Grant
        grants = list(Grant.objects.using(tenant_db).order_by("code").values_list("id", "code", "title")[:200])
        if hasattr(user, "assigned_grants"):
            selected_grant_ids = list(user.assigned_grants.values_list("id", flat=True))
    except Exception:
        pass

    if request.method == "POST":
        before = {
            "full_name": user.full_name,
            "phone_number": user.phone_number,
            "department": user.department,
            "is_active": user.is_active,
        }
        user.full_name = (request.POST.get("full_name") or "").strip()[:200]
        user.phone_number = (request.POST.get("phone_number") or "").strip()[:30]
        user.department = (request.POST.get("department") or "").strip()[:120]
        user.is_active = request.POST.get("status") != "inactive"
        user.save(update_fields=["full_name", "phone_number", "department", "is_active"])
        role_id = request.POST.get("role_id")
        UserRole.objects.using(tenant_db).filter(user=user).delete()
        previous_role = None
        ur_existing = UserRole.objects.using(tenant_db).filter(user=user).first()
        if ur_existing:
            previous_role = ur_existing.role.name
        if role_id:
            try:
                role = Role.objects.using(tenant_db).get(pk=int(role_id))
                UserRole.objects.using(tenant_db).create(user=user, role=role)
            except (ValueError, Role.DoesNotExist):
                pass
        if hasattr(user, "assigned_grants"):
            user.assigned_grants.set([])
            grant_ids = request.POST.getlist("assigned_grants")
            try:
                from tenant_grants.models import Grant
                for gid in grant_ids:
                    try:
                        g = Grant.objects.using(tenant_db).get(pk=int(gid))
                        user.assigned_grants.add(g)
                    except (ValueError, Grant.DoesNotExist):
                        pass
            except Exception:
                pass
        # Audit log: user update (profile, role, project assignments)
        AuditLog.objects.using(tenant_db).create(
            model_name="tenantuser",
            object_id=user.id,
            action=AuditLog.Action.UPDATE,
            user_id=request.tenant_user.id if request.tenant_user else None,
            username=request.tenant_user.get_full_name() if getattr(request, "tenant_user", None) else "",
            summary=f"User updated: {user.email} (role: {role.name if role_id else previous_role or 'N/A'}).",
            old_data={
                **before,
                "role": previous_role,
            },
            new_data={
                "full_name": user.full_name,
                "phone_number": user.phone_number,
                "department": user.department,
                "is_active": user.is_active,
                "role": role.name if role_id and 'role' in locals() else previous_role,
                "assigned_grants": list(user.assigned_grants.values_list("id", flat=True))
                if hasattr(user, "assigned_grants") else [],
            },
        )
        messages.success(request, f"User {user.email} has been updated.")
        return redirect(reverse("tenant_portal:user_management"))

    current_role_id = None
    ur = UserRole.objects.using(tenant_db).filter(user=user).first()
    if ur:
        current_role_id = ur.role_id

    return render(
        request,
        "tenant_portal/user_management_form.html",
        {
            "tenant": request.tenant,
            "tenant_user": request.tenant_user,
            "target_user": user,
            "roles": roles,
            "grants": grants,
            "selected_grant_ids": selected_grant_ids,
            "current_role_id": current_role_id,
            "is_add": False,
        },
    )


@tenant_view(require_perm="users:manage")
def user_management_deactivate_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Set user to inactive. Block if target is current user (admin cannot deactivate themselves)."""
    if request.method != "POST":
        return redirect(reverse("tenant_portal:user_management"))
    tenant_db = request.tenant_db
    user = get_object_or_404(TenantUser.objects.using(tenant_db), pk=pk)
    if user.id == request.tenant_user.id:
        messages.error(request, "You cannot deactivate your own account.")
        return redirect(reverse("tenant_portal:user_management"))
    user.is_active = False
    user.save(update_fields=["is_active"])
    # Audit log: user deactivation (soft-delete)
    AuditLog.objects.using(tenant_db).create(
        model_name="tenantuser",
        object_id=user.id,
        action=AuditLog.Action.UPDATE,
        user_id=request.tenant_user.id if request.tenant_user else None,
        username=request.tenant_user.get_full_name() if getattr(request, "tenant_user", None) else "",
        summary=f"User deactivated: {user.email}.",
    )
    messages.success(request, f"User {user.email} has been deactivated.")
    return redirect(reverse("tenant_portal:user_management"))


@tenant_view(require_perm="users:manage")
def user_management_reset_password_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Set a new password for the user."""
    tenant_db = request.tenant_db
    user = get_object_or_404(TenantUser.objects.using(tenant_db), pk=pk)
    if request.method == "POST":
        new_password = (request.POST.get("new_password") or "").strip()
        confirm = (request.POST.get("confirm_password") or "").strip()
        if len(new_password) < 8:
            messages.error(request, "Password must be at least 8 characters.")
        elif new_password != confirm:
            messages.error(request, "Password and confirmation do not match.")
        else:
            user.set_password(new_password)
            user.save(update_fields=["password_hash"])
            AuditLog.objects.using(tenant_db).create(
                model_name="tenantuser",
                object_id=user.id,
                action=AuditLog.Action.UPDATE,
                user_id=request.tenant_user.id if request.tenant_user else None,
                username=request.tenant_user.get_full_name() if getattr(request, "tenant_user", None) else "",
                summary=f"Password reset for user: {user.email}.",
            )
            messages.success(request, f"Password has been reset for {user.email}.")
            return redirect(reverse("tenant_portal:user_management_view", kwargs={"pk": user.pk}))
    return render(
        request,
        "tenant_portal/user_management_reset_password.html",
        {
            "tenant": request.tenant,
            "tenant_user": request.tenant_user,
            "target_user": user,
        },
    )
