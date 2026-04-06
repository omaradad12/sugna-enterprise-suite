from django.urls import path, reverse_lazy
from django.views.generic.base import RedirectView

from . import views

app_name = "website"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("about/", views.AboutView.as_view(), name="about"),
    path("modules/<slug:slug>/", views.ModuleDetailView.as_view(), name="module_detail"),
    path("modules/", views.ModulesView.as_view(), name="modules"),
    path("enterprise-platform/", views.PlatformView.as_view(), name="platform"),
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
    # Sugna Academy — central learning umbrella (legacy /training/* URLs redirect here)
    path("academy/", views.AcademyHomeView.as_view(), name="academy_home"),
    path("academy/courses/", views.AcademyCoursesView.as_view(), name="academy_courses"),
    path("academy/learning-paths/", views.AcademyLearningPathsView.as_view(), name="academy_learning_paths"),
    path("academy/certifications/", views.AcademyCertificationsView.as_view(), name="academy_certifications"),
    path("academy/tutorials/", views.AcademyTutorialsView.as_view(), name="academy_tutorials"),
    path("academy/webinars/", views.AcademyWebinarsView.as_view(), name="academy_webinars"),
    path("academy/documentation/", views.AcademyDocumentationView.as_view(), name="academy_documentation"),
    path("academy/help/", views.AcademyHelpView.as_view(), name="academy_help"),
    path(
        "training/",
        RedirectView.as_view(pattern_name="website:academy_home", permanent=True),
        name="training",
    ),
    path(
        "training/role-based/",
        RedirectView.as_view(pattern_name="website:academy_learning_paths", permanent=True),
        name="training_role_based",
    ),
    path(
        "training/webinars/",
        RedirectView.as_view(pattern_name="website:academy_webinars", permanent=True),
        name="training_webinars",
    ),
    path(
        "training/certification/",
        RedirectView.as_view(pattern_name="website:academy_certifications", permanent=True),
        name="training_certification",
    ),
    path(
        "training/support/",
        RedirectView.as_view(pattern_name="website:academy_help", permanent=True),
        name="training_support",
    ),
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
