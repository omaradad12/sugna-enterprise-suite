from django.contrib import admin

from tenant_hospital.models import (
    Admission,
    Appointment,
    Bed,
    ClinicalNote,
    Department,
    EmergencyVisit,
    Encounter,
    InsurancePlan,
    LabOrder,
    LabOrderLine,
    OutpatientVisit,
    Patient,
    PatientDocument,
    PatientInsurance,
    PatientInvoice,
    PharmacyOrder,
    PharmacyOrderLine,
    Provider,
    VitalSign,
    Ward,
)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ("full_name", "provider_type", "department", "is_active")
    list_filter = ("provider_type", "is_active", "department")
    search_fields = ("full_name", "license_number", "email")


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("mrn", "full_name", "gender", "date_of_birth", "phone", "is_active")
    list_filter = ("gender", "is_active")
    search_fields = ("mrn", "full_name", "phone", "email")


@admin.register(PatientDocument)
class PatientDocumentAdmin(admin.ModelAdmin):
    list_display = ("patient", "title", "uploaded_at")
    autocomplete_fields = ("patient",)


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("start_at", "end_at", "patient", "provider", "department", "status")
    list_filter = ("status", "department")
    search_fields = ("patient__mrn", "patient__full_name", "provider__full_name", "reason")
    autocomplete_fields = ("patient", "provider", "department")


@admin.register(Encounter)
class EncounterAdmin(admin.ModelAdmin):
    list_display = ("started_at", "ended_at", "patient", "provider", "appointment")
    search_fields = ("patient__mrn", "patient__full_name", "provider__full_name", "chief_complaint")
    autocomplete_fields = ("patient", "provider", "appointment")


@admin.register(VitalSign)
class VitalSignAdmin(admin.ModelAdmin):
    list_display = ("recorded_at", "encounter", "bp_systolic", "bp_diastolic", "heart_rate", "temperature_c")
    list_filter = ("encounter",)
    autocomplete_fields = ("encounter",)


@admin.register(ClinicalNote)
class ClinicalNoteAdmin(admin.ModelAdmin):
    list_display = ("created_at", "encounter", "note_type", "author_provider")
    autocomplete_fields = ("encounter", "author_provider")


@admin.register(LabOrder)
class LabOrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "patient", "status", "ordered_at")
    list_filter = ("status",)
    search_fields = ("order_number", "patient__mrn", "patient__full_name")
    autocomplete_fields = ("patient", "encounter", "ordered_by")


@admin.register(LabOrderLine)
class LabOrderLineAdmin(admin.ModelAdmin):
    list_display = ("lab_order", "test_name", "status")
    autocomplete_fields = ("lab_order",)


@admin.register(PharmacyOrder)
class PharmacyOrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "patient", "status", "ordered_at")
    list_filter = ("status",)
    search_fields = ("order_number", "patient__mrn")
    autocomplete_fields = ("patient", "encounter", "ordered_by")


@admin.register(PharmacyOrderLine)
class PharmacyOrderLineAdmin(admin.ModelAdmin):
    list_display = ("pharmacy_order", "medication_name", "dose")
    autocomplete_fields = ("pharmacy_order",)


@admin.register(Ward)
class WardAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "floor", "is_active")
    search_fields = ("code", "name")


@admin.register(Bed)
class BedAdmin(admin.ModelAdmin):
    list_display = ("ward", "room_label", "bed_label", "status")
    list_filter = ("status", "ward")
    search_fields = ("room_label", "bed_label", "ward__code", "ward__name")
    autocomplete_fields = ("ward",)


@admin.register(Admission)
class AdmissionAdmin(admin.ModelAdmin):
    list_display = ("patient", "bed", "status", "admitted_at", "discharged_at", "attending_provider")
    list_filter = ("status",)
    autocomplete_fields = ("patient", "bed", "encounter", "attending_provider")


@admin.register(InsurancePlan)
class InsurancePlanAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "payer_name", "is_active")
    search_fields = ("code", "name")


@admin.register(PatientInsurance)
class PatientInsuranceAdmin(admin.ModelAdmin):
    list_display = ("patient", "plan", "policy_number", "is_primary")
    autocomplete_fields = ("patient", "plan")


@admin.register(PatientInvoice)
class PatientInvoiceAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "patient", "status", "total_amount", "currency", "issued_at")
    list_filter = ("status", "currency")
    search_fields = ("invoice_number", "patient__mrn")
    autocomplete_fields = ("patient", "encounter")
