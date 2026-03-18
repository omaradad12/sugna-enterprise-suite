from django.urls import path
from . import views

app_name = "diagnostics_api"

urlpatterns = [
    path("health/", views.health),
    path("scan/", views.scan_view),
    path("reports/", views.reports_list),
    path("reports/<int:report_id>/", views.report_detail),
    path("checks/runs/", views.check_runs_list),
    path("checks/runs/<int:run_id>/", views.check_run_detail),
    path("findings/", views.findings_list),
    path("incidents/", views.incidents_list),
    path("incidents/<int:incident_id>/", views.incident_detail),
    path("incidents/<int:incident_id>/remediate/", views.incident_remediate),
    path("remediation-logs/", views.remediation_logs_list),
]
