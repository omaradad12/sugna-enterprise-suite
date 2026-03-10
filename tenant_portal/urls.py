from django.urls import path

from . import views

app_name = "tenant_portal"

urlpatterns = [
    path("login/", views.tenant_login_view, name="login"),
    path("logout/", views.tenant_logout_view, name="logout"),
    path("", views.tenant_home_view, name="home"),
    # Finance
    path("finance/", views.finance_home_view, name="finance_home"),
    path("finance/accounts/", views.finance_accounts_view, name="finance_accounts"),
    path("finance/journals/", views.finance_journals_view, name="finance_journals"),
    # Grant Management
    path("grants/", views.grants_home_view, name="grants_home"),
    path("grants/donors/", views.grants_donors_view, name="grants_donors"),
    path("grants/grants/", views.grants_grants_view, name="grants_grants"),
    path("grants/budgets/", views.grants_budgets_view, name="grants_budgets"),
    path("grants/approvals/", views.grants_approvals_view, name="grants_approvals"),
    path("grants/reports/", views.grants_reports_view, name="grants_reports"),
    # Integrations
    path("integrations/", views.integrations_home_view, name="integrations_home"),
    path("integrations/webhooks/", views.integrations_webhooks_view, name="integrations_webhooks"),
    path("integrations/erp/", views.integrations_erp_view, name="integrations_erp"),
]

