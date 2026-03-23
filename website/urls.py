from django.urls import path

from . import views

app_name = "website"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("about/", views.AboutView.as_view(), name="about"),
    path("modules/", views.ModulesView.as_view(), name="modules"),
    path("solutions/", views.SolutionsView.as_view(), name="solutions"),
    path("features/", views.FeaturesView.as_view(), name="features"),
    path("industries/", views.IndustriesView.as_view(), name="industries"),
    path("pricing/", views.PricingView.as_view(), name="pricing"),
    path("training/", views.TrainingView.as_view(), name="training"),
    path("demo-request/", views.demo_request_view, name="demo_request"),
    path("support/", views.SupportView.as_view(), name="support"),
    path("contact/", views.contact_view, name="contact"),
    path("blog/", views.BlogView.as_view(), name="blog"),
    path("privacy/", views.PrivacyView.as_view(), name="privacy"),
    path("terms/", views.TermsView.as_view(), name="terms"),
    path("login-portal/", views.LoginPortalView.as_view(), name="login_portal"),
]
