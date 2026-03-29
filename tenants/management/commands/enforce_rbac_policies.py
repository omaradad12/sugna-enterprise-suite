from __future__ import annotations

from django.core.management.base import BaseCommand

from tenants.db import ensure_tenant_db_configured, tenant_db_alias
from tenants.models import Tenant


class Command(BaseCommand):
    help = "Enforce system RBAC policy: roles, module access, maker-checker, and scope defaults."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", help="Tenant slug or ID. If omitted, applies to all provisioned tenants.")

    def handle(self, *args, **options):
        tenant_arg = (options.get("tenant") or "").strip()
        if tenant_arg:
            tenant = Tenant.objects.filter(slug=tenant_arg).first() or Tenant.objects.filter(pk=tenant_arg).first()
            tenants = [tenant] if tenant else []
        else:
            tenants = list(Tenant.objects.filter(db_name__isnull=False).exclude(db_name="").order_by("id"))

        if not tenants:
            self.stdout.write("No tenants found.")
            return

        from rbac.models import Permission, Role, RolePermission

        role_sets = {
            # Admin manages users/roles and sees directory, but cannot create/approve/post financial transactions.
            "Tenant Admin": {
                "is_system": True,
                "role_type": "admin",
                "perms": {
                    "users:manage",
                    "rbac:roles.manage",
                    "module:modules.manage",
                    "module:finance.view",
                    "finance:journals.view",
                    "finance:vouchers.view",
                    "finance:payments.view",
                    "finance:reporting.view",
                    "finance:reporting.export",
                    "finance:audit.view",
                    "dashboard:view",
                },
            },
            # Full control + approvals
            "Finance Manager": {
                "is_system": True,
                "role_type": "financial",
                "perms": {
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
                    "finance:journals.adjusting",
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
                    "finance:bankcash.view",
                    "finance:bankcash.manage",
                    "finance:reconciliation.view",
                    "finance:reconciliation.manage",
                    "finance:reconciliation.post",
                    "finance:audit.view",
                    "finance:periods.view",
                    "finance:periods.close",
                    "finance:periods.reopen",
                    "finance:posting.backdated",
                    "finance:locking.lock",
                    "finance:locking.unlock",
                    "finance:transactions.reverse",
                    "finance:attachments.view",
                    "finance:attachments.upload",
                    "dashboard:view",
                },
            },
            # Accountant: journal entry and adjusting journals (NGO); submit only — approval/post by Finance Manager.
            "Accountant": {
                "is_system": True,
                "role_type": "financial",
                "perms": {
                    "module:finance.view",
                    "finance:journals.view",
                    "finance:journals.create",
                    "finance:journals.edit",
                    "finance:journals.delete",
                    "finance:journals.adjusting",
                    "finance:reporting.view",
                    "finance:reporting.export",
                    "finance:attachments.view",
                    "finance:attachments.upload",
                    "dashboard:view",
                },
            },
            # Project-level finance officer (maker, no checker)
            "Finance Officer": {
                "is_system": True,
                "role_type": "financial",
                "perms": {
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
                },
            },
            # Cashier: cashbook only (view)
            "Cashier": {
                "is_system": True,
                "role_type": "operational",
                "perms": {
                    "module:main_cashbook.view",
                    "cashbook:entries.view",
                },
            },
            # Program Manager: read-only across assigned projects
            "Program Manager": {
                "is_system": True,
                "role_type": "operational",
                "perms": {
                    "module:finance.view",
                    "finance:journals.view",
                    "finance:vouchers.view",
                    "finance:payments.view",
                    "finance:reporting.view",
                    "finance:reporting.export",
                    "dashboard:view",
                },
            },
        }

        for tenant in tenants:
            if not tenant:
                continue
            ensure_tenant_db_configured(tenant)
            alias = tenant_db_alias(tenant)

            # Ensure system roles exist and their permissions match policy.
            for role_name, spec in role_sets.items():
                role, _ = Role.objects.using(alias).get_or_create(
                    name=role_name,
                    defaults={
                        "description": "System role",
                        "is_system": bool(spec.get("is_system")),
                        "role_type": (spec.get("role_type") or Role.RoleType.OPERATIONAL),
                    },
                )
                if bool(spec.get("is_system")) and not role.is_system:
                    role.is_system = True
                    role.save(using=alias, update_fields=["is_system"])
                desired_role_type = spec.get("role_type") or getattr(role, "role_type", "") or Role.RoleType.OPERATIONAL
                if getattr(role, "role_type", "") != desired_role_type:
                    role.role_type = desired_role_type
                    role.save(using=alias, update_fields=["role_type"])

                desired = set(spec.get("perms") or set())
                desired_perms = list(Permission.objects.using(alias).filter(code__in=desired))
                desired_ids = {p.id for p in desired_perms}

                existing_ids = set(
                    RolePermission.objects.using(alias)
                    .filter(role_id=role.id)
                    .values_list("permission_id", flat=True)
                )

                # Add missing
                for pid in desired_ids - existing_ids:
                    RolePermission.objects.using(alias).get_or_create(role_id=role.id, permission_id=pid)
                # Remove extras from system role
                RolePermission.objects.using(alias).filter(role_id=role.id, permission_id__in=(existing_ids - desired_ids)).delete()

            self.stdout.write(self.style.SUCCESS(f"Enforced RBAC policy for tenant '{tenant.slug}' ({alias})."))  # noqa: T201

