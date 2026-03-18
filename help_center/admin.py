from django.contrib import admin
from django.utils.html import format_html

from .models import HelpCategory, HelpContent, SupportTicket


@admin.register(HelpCategory)
class HelpCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "display_order")
    list_editable = ("display_order",)
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug")


@admin.register(HelpContent)
class HelpContentAdmin(admin.ModelAdmin):
    list_display = ("title", "content_type", "category", "is_published", "display_order", "updated_at")
    list_filter = ("content_type", "is_published", "category")
    list_editable = ("is_published", "display_order")
    search_fields = ("title", "body")
    prepopulated_fields = {"slug": ("title",)}
    raw_id_fields = ("category",)


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ("id", "subject", "tenant", "user_email", "status", "priority", "created_at", "assigned_to")
    list_filter = ("status", "priority", "tenant")
    search_fields = ("subject", "body", "user_email", "user_name")
    raw_id_fields = ("tenant", "assigned_to")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("tenant", "tenant_user_id", "user_email", "user_name", "subject", "body")}),
        ("Status", {"fields": ("status", "priority", "assigned_to")}),
        ("Support", {"fields": ("support_notes", "support_response", "responded_at")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
