from django.urls import path
from . import views

app_name = "platform_dashboard"

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path("logo.png", views.logo_view, name="logo"),
    path("dashboard/", views.dashboard_view, name="dashboard_home"),
    path("tenants/", views.tenant_list_view, name="tenant_list"),
    path("tenants/register/", views.tenant_register_view, name="tenant_register"),
    path("tenants/<int:pk>/", views.tenant_detail_view, name="tenant_detail"),
    path("users/", views.platform_users_view, name="platform_users"),
    path("users/reset-password/", views.platform_reset_tenant_user_password_view, name="platform_reset_tenant_user_password"),
    path("users/set-password/", views.platform_set_tenant_user_password_view, name="platform_set_tenant_user_password"),
    path("modules/", views.module_list_view, name="module_list"),
    path("modules/workplace/", views.module_workplace_preview_view, name="module_workplace_preview"),
    path("diagnostics/", views.diagnostics_view, name="diagnostics"),
    path("diagnostics/run-scan/", views.diagnostics_run_scan_view, name="diagnostics_run_scan"),
    path("diagnostics/reports/<int:report_id>/", views.diagnostics_report_view, name="diagnostics_report"),
]
