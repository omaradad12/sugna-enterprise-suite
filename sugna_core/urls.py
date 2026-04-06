"""
URL configuration for sugna_core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

from . import views
from website import views as website_views

handler404 = website_views.page_not_found_view

urlpatterns = [
    # Platform and admin must come before path("", include("website.urls")) so /platform/
    # hits platform_dashboard (staff UI), not website.PlatformView.
    path("platform/login/", auth_views.LoginView.as_view(template_name="platform_dashboard/platform_login.html"), name="platform_login"),
    # Reuse the platform login UI for Django admin login as well, so the
    # look-and-feel is identical across "Admin" and "Platform".
    path("admin/login/", auth_views.LoginView.as_view(template_name="platform_dashboard/platform_login.html"), name="admin_login"),
    path(
        "platform/password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="platform_dashboard/password_reset_form.html",
            email_template_name="platform_dashboard/password_reset_email.txt",
            subject_template_name="platform_dashboard/password_reset_subject.txt",
            success_url="/platform/password-reset/done/",
        ),
        name="password_reset",
    ),
    path(
        "platform/password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(template_name="platform_dashboard/password_reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "platform/reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="platform_dashboard/password_reset_confirm.html",
            success_url="/platform/reset/done/",
        ),
        name="password_reset_confirm",
    ),
    path(
        "platform/reset/done/",
        auth_views.PasswordResetCompleteView.as_view(template_name="platform_dashboard/password_reset_complete.html"),
        name="password_reset_complete",
    ),
    path("admin/logout/", views.admin_logout_view, name="admin_logout"),
    path("platform/logout/", views.platform_logout_view, name="platform_logout"),
    path("admin/", admin.site.urls),
    path("platform/", include("platform_dashboard.urls")),
    path("t/", include("tenant_portal.urls")),
    path("api/diagnostics/", include("diagnostics.api.urls")),
    # path("api/ai-auditor/", include("ai_auditor.api.urls")),  # enable when ai_auditor app exists
    path("", include("website.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # Serve STATICFILES_DIRS (e.g. project static/assets/...) when using ASGI (uvicorn/daphne)
    # or any server that does not wrap the app with StaticFilesHandler.
    urlpatterns += staticfiles_urlpatterns()
