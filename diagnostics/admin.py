from django.contrib import admin
from .models import (
    DiagnosticReport,
    DiagnosticCheckRun,
    Finding,
    Incident,
    RemediationLog,
    RemediationPolicy,
    LogEvent,
)


@admin.register(DiagnosticReport)
class DiagnosticReportAdmin(admin.ModelAdmin):
    list_display = ("id", "trigger", "status", "target", "started_at", "finished_at")
    list_filter = ("trigger", "status")
    readonly_fields = ("started_at", "finished_at", "created_at")


@admin.register(DiagnosticCheckRun)
class DiagnosticCheckRunAdmin(admin.ModelAdmin):
    list_display = ("id", "scope", "tenant_slug", "check_type", "status", "duration_ms", "created_at")
    list_filter = ("scope", "status", "check_type")
    search_fields = ("message", "tenant_slug")
    readonly_fields = ("created_at",)


@admin.register(Finding)
class FindingAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "title", "severity", "tenant_id", "run", "created_at")
    list_filter = ("severity", "code")
    search_fields = ("title", "code")
    readonly_fields = ("created_at",)


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "severity", "status", "scope", "tenant_slug", "created_at")
    list_filter = ("status", "severity", "scope")
    search_fields = ("title", "tenant_slug")
    readonly_fields = ("created_at", "updated_at", "resolved_at")


@admin.register(RemediationLog)
class RemediationLogAdmin(admin.ModelAdmin):
    list_display = ("id", "incident", "action_code", "status", "started_at", "finished_at")
    list_filter = ("status", "action_code")
    readonly_fields = ("started_at",)


@admin.register(RemediationPolicy)
class RemediationPolicyAdmin(admin.ModelAdmin):
    list_display = ("action_code", "allowed", "require_approval", "updated_at")


@admin.register(LogEvent)
class LogEventAdmin(admin.ModelAdmin):
    list_display = ("id", "source", "level", "tenant_id", "timestamp", "created_at")
    list_filter = ("source", "level")
    readonly_fields = ("created_at",)
