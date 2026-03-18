from django.contrib import admin
from .models import (
    TransactionRiskAssessment,
    RiskAlert,
    InvestigationCase,
    InvestigationNote,
    InvestigationAttachment,
    ControlRule,
    AuditFinding,
    AuditScreeningSession,
    ScreeningUploadFile,
)


@admin.register(TransactionRiskAssessment)
class TransactionRiskAssessmentAdmin(admin.ModelAdmin):
    list_display = ("source_type", "source_id", "risk_score", "risk_level", "assessed_at")
    list_filter = ("risk_level", "source_type")
    search_fields = ("indicator_summary",)


@admin.register(RiskAlert)
class RiskAlertAdmin(admin.ModelAdmin):
    list_display = ("title", "alert_type", "severity", "status", "created_at")
    list_filter = ("alert_type", "severity", "status")


class InvestigationNoteInline(admin.TabularInline):
    model = InvestigationNote
    extra = 0


class InvestigationAttachmentInline(admin.TabularInline):
    model = InvestigationAttachment
    extra = 0


@admin.register(InvestigationCase)
class InvestigationCaseAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "priority", "created_at")
    list_filter = ("status", "priority")
    inlines = [InvestigationNoteInline, InvestigationAttachmentInline]


@admin.register(ControlRule)
class ControlRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "rule_type", "is_active")
    list_filter = ("rule_type", "is_active")


@admin.register(AuditFinding)
class AuditFindingAdmin(admin.ModelAdmin):
    list_display = (
        "title", "finding_stage", "is_actual", "is_realized", "status",
        "financial_impact", "recovered_amount", "recovery_status", "due_date", "created_at",
    )
    list_filter = ("finding_stage", "is_actual", "is_realized", "status", "recovery_status")
    search_fields = ("title", "description", "root_cause")


class ScreeningUploadFileInline(admin.TabularInline):
    model = ScreeningUploadFile
    extra = 0
    readonly_fields = ("temp_file_path", "original_filename", "file_size", "uploaded_at")
    can_delete = True


@admin.register(AuditScreeningSession)
class AuditScreeningSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "auditor_user_id", "status", "case", "created_at", "expires_at", "finished_at")
    list_filter = ("status",)
    readonly_fields = ("created_at", "expires_at", "finished_at")
    inlines = [ScreeningUploadFileInline]
