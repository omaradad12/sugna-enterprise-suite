from django.urls import path

from platform_announcements import views as announcement_views
from platform_email_templates import views as email_template_views

from . import views

app_name = "platform_dashboard"

urlpatterns = [
    path("coming-soon/<slug>/", views.platform_coming_soon_view, name="coming_soon"),
    path("", views.dashboard_view, name="dashboard"),
    path("logo.png", views.logo_view, name="logo"),
    path("dashboard/", views.dashboard_view, name="dashboard_home"),
    path("tenants/", views.tenant_list_view, name="tenant_list"),
    path("tenants/register/", views.tenant_register_view, name="tenant_register"),
    path("tenants/check-domain/", views.tenant_domain_availability_view, name="tenant_check_domain"),
    path("tenants/<int:pk>/edit/", views.tenant_edit_view, name="tenant_edit"),
    path("tenants/<int:pk>/", views.tenant_detail_view, name="tenant_detail"),
    path("users/", views.platform_users_view, name="platform_users"),
    path("users/reset-password/", views.platform_reset_tenant_user_password_view, name="platform_reset_tenant_user_password"),
    path("users/set-password/", views.platform_set_tenant_user_password_view, name="platform_set_tenant_user_password"),
    path("modules/", views.module_list_view, name="module_list"),
    path("modules/workplace/", views.module_workplace_preview_view, name="module_workplace_preview"),
    path("modules/workplace/go/", views.module_workplace_dispatch_view, name="module_workplace_go"),
    path("help-center/", views.platform_help_center_view, name="help_center"),
    path("integrations/", views.platform_integrations_hub_view, name="integrations_hub"),
    path("diagnostics/", views.diagnostics_view, name="diagnostics"),
    path("diagnostics/run-scan/", views.diagnostics_run_scan_view, name="diagnostics_run_scan"),
    path("diagnostics/reports/<int:report_id>/", views.diagnostics_report_view, name="diagnostics_report"),
    path("announcements/", announcement_views.announcement_list_view, name="announcement_list"),
    path("announcements/new/", announcement_views.announcement_create_view, name="announcement_create"),
    path("announcements/<int:pk>/edit/", announcement_views.announcement_edit_view, name="announcement_edit"),
    path("announcements/<int:pk>/delete/", announcement_views.announcement_delete_view, name="announcement_delete"),
    path("announcements/<int:pk>/publish/", announcement_views.announcement_publish_view, name="announcement_publish"),
    path("announcements/<int:pk>/unpublish/", announcement_views.announcement_unpublish_view, name="announcement_unpublish"),
    path("email-templates/", email_template_views.email_template_list_view, name="email_template_list"),
    path("email-templates/new/", email_template_views.email_template_create_view, name="email_template_create"),
    path("email-templates/<int:pk>/edit/", email_template_views.email_template_edit_view, name="email_template_edit"),
    path("email-templates/<int:pk>/delete/", email_template_views.email_template_delete_view, name="email_template_delete"),
    path("email-templates/<int:pk>/preview/", email_template_views.email_template_preview_view, name="email_template_preview"),
]
