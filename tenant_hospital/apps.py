from django.apps import AppConfig


class TenantHospitalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tenant_hospital"
    verbose_name = "Hospital Management"

