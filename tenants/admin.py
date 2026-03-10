from django.contrib import admin

from tenants.models import Tenant, Module


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "domain", "status", "plan", "is_active", "user_count", "subscription_expiry", "created_at")
    list_filter = ("is_active", "status", "modules")
    search_fields = ("name", "slug", "domain", "country")
    filter_horizontal = ("modules",)
    list_editable = ("status", "plan")

