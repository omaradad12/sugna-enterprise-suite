from django.urls import path, reverse_lazy
from django.views.generic.base import RedirectView

from . import views

app_name = "website"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("about/", views.AboutView.as_view(), name="about"),
    path("modules/<slug:slug>/", views.ModuleDetailView.as_view(), name="module_detail"),
    path("modules/", views.ModulesView.as_view(), name="modules"),
    path("platform/", views.PlatformView.as_view(), name="platform"),
    path("solutions/", views.SolutionsView.as_view(), name="solutions"),
    path("features/", views.FeaturesView.as_view(), name="features"),
    path("industries/", views.IndustriesView.as_view(), name="industries"),
    path(
        "pricing/subscriptions/",
        views.PricingSubscriptionsView.as_view(),
        name="pricing_subscriptions",
    ),
    path(
        "pricing/onboarding/",
        views.PricingOnboardingView.as_view(),
        name="pricing_onboarding",
    ),
    path(
        "pricing/partnerships/",
        RedirectView.as_view(pattern_name="website:pricing_subscriptions", permanent=True),
    ),
    path(
        "pricing/editions/",
        RedirectView.as_view(pattern_name="website:pricing_subscriptions", permanent=True),
    ),
    path(
        "pricing/compare/",
        RedirectView.as_view(pattern_name="website:pricing_subscriptions", permanent=True),
    ),
    path(
        "pricing/implementation/",
        RedirectView.as_view(pattern_name="website:pricing_onboarding", permanent=True),
    ),
    path(
        "pricing/partners/",
        RedirectView.as_view(pattern_name="website:pricing_subscriptions", permanent=True),
    ),
    path(
        "pricing/",
        RedirectView.as_view(pattern_name="website:pricing_subscriptions", permanent=False),
        name="pricing",
    ),
    path("training/", views.TrainingView.as_view(), name="training"),
    path("training/role-based/", views.TrainingRoleBasedView.as_view(), name="training_role_based"),
    path("training/webinars/", views.TrainingWebinarsView.as_view(), name="training_webinars"),
    path("training/certification/", views.TrainingCertificationView.as_view(), name="training_certification"),
    path("training/support/", views.TrainingSupportView.as_view(), name="training_support"),
    path("resources/", views.ResourcesView.as_view(), name="resources"),
    path("demo-request/", views.demo_request_view, name="demo_request"),
    path("support/", views.SupportView.as_view(), name="support"),
    path("contact/", views.contact_view, name="contact"),
    path("blog/", views.BlogView.as_view(), name="blog"),
    path("privacy/", views.PrivacyView.as_view(), name="privacy"),
    path("terms/", views.TermsView.as_view(), name="terms"),
    path("login-portal/", views.LoginPortalView.as_view(), name="login_portal"),
    path(
        "customer-portal/",
        views.CustomerPortalAccessView.as_view(),
        name="customer_portal_home",
    ),
    path(
        "customer-portal/dashboard/",
        views.CustomerPortalDashboardView.as_view(),
        name="customer_portal_dashboard",
    ),
    path(
        "customer-portal/downloads/",
        RedirectView.as_view(
            url=reverse_lazy("website:customer_portal_section", kwargs={"slug": "templates"}),
            permanent=True,
        ),
    ),
    path(
        "customer-portal/<slug:slug>/",
        views.CustomerPortalSectionView.as_view(),
        name="customer_portal_section",
    ),
]
