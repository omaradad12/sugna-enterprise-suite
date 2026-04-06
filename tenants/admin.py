from django.contrib import admin

from tenants.models import Module, SubscriptionPlan, Tenant, TenantBrandingProfile, TenantModule


class TenantBrandingProfileInline(admin.StackedInline):
    """Visual identity and post-login behavior (one row per tenant)."""

    model = TenantBrandingProfile
    extra = 0
    max_num = 1
    can_delete = False


class TenantModuleInline(admin.TabularInline):
    """Per-tenant subscription: tick «is enabled» and add modules (e.g. Audit & Risk) from the catalog."""

    model = TenantModule
    extra = 0
    autocomplete_fields = ("module",)
    readonly_fields = ("enabled_at",)
    verbose_name_plural = "Enabled modules (subscription)"


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")
    ordering = ("sort_order", "code")


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "category", "sort_order", "is_active")
    list_filter = ("is_active", "category")
    search_fields = ("code", "name", "description")
    ordering = ("sort_order", "code")


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "domain",
        "provisioning_status",
        "db_name",
        "status",
        "plan",
        "is_active",
        "user_count",
        "subscription_expiry",
        "created_at",
    )
    list_filter = ("is_active", "status", "provisioning_status")
    readonly_fields = ("provisioned_at", "provisioning_error", "created_at", "updated_at")
    search_fields = ("name", "slug", "domain", "country")
    inlines = (TenantBrandingProfileInline, TenantModuleInline)
    list_editable = ("status", "plan")


@admin.register(TenantModule)
class TenantModuleAdmin(admin.ModelAdmin):
    list_display = ("tenant", "module", "is_enabled", "enabled_at")
    list_filter = ("is_enabled", "module")
    search_fields = ("tenant__name", "tenant__slug", "module__code")
    autocomplete_fields = ("tenant", "module")
