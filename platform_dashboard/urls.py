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
    path("modules/", views.module_list_view, name="module_list"),
    path("modules/workplace/", views.module_workplace_preview_view, name="module_workplace_preview"),
]
