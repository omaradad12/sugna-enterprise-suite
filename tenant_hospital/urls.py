"""
Hospital Management routes (namespace: hospital).

Mounted at tenant_portal URLconf under path("hospital/", …), so final paths are
/t/hospital/… (middleware may rewrite /t/<slug>/hospital/… to this inner path).
"""

from django.urls import path

from tenant_portal import views_hospital as vh
from tenant_portal import views_hospital_extended as vhx

urlpatterns = [
    path("", vh.hospital_home_view, name="hospital_home"),
    path("setup/", vh.hospital_setup_hub_view, name="hospital_setup"),
    path("departments/", vh.hospital_departments_view, name="hospital_departments"),
    path("providers/", vh.hospital_providers_view, name="hospital_providers"),
    path("patients/", vh.hospital_patients_view, name="hospital_patients"),
    path("patients/create/", vh.hospital_patient_create_view, name="hospital_patient_create"),
    path("patients/<int:patient_id>/", vh.hospital_patient_detail_view, name="hospital_patient_detail"),
    path("visits/opd/", vh.hospital_opd_list_view, name="hospital_opd_list"),
    path("visits/opd/create/", vh.hospital_opd_visit_create_view, name="hospital_opd_visit_create"),
    path("visits/emergency/", vh.hospital_emergency_list_view, name="hospital_emergency_list"),
    path("visits/emergency/create/", vh.hospital_emergency_visit_create_view, name="hospital_emergency_visit_create"),
    path("appointments/", vh.hospital_appointments_view, name="hospital_appointments"),
    path("appointments/create/", vh.hospital_appointment_create_view, name="hospital_appointment_create"),
    path(
        "appointments/<int:appointment_id>/encounter/create/",
        vh.hospital_encounter_create_view,
        name="hospital_encounter_create",
    ),
    path("encounters/<int:encounter_id>/", vhx.hospital_encounter_detail_view, name="hospital_encounter_detail"),
    path(
        "encounters/<int:encounter_id>/vitals/add/",
        vhx.hospital_encounter_vital_add_view,
        name="hospital_encounter_vital_add",
    ),
    path(
        "encounters/<int:encounter_id>/notes/add/",
        vhx.hospital_encounter_note_add_view,
        name="hospital_encounter_note_add",
    ),
    path(
        "encounters/<int:encounter_id>/lab-order/add/",
        vhx.hospital_encounter_lab_order_add_view,
        name="hospital_encounter_lab_order_add",
    ),
    path(
        "encounters/<int:encounter_id>/rx-order/add/",
        vhx.hospital_encounter_rx_order_add_view,
        name="hospital_encounter_rx_order_add",
    ),
    path("lab-orders/", vhx.hospital_lab_orders_view, name="hospital_lab_orders"),
    path("pharmacy-orders/", vhx.hospital_pharmacy_orders_view, name="hospital_pharmacy_orders"),
    path("inpatient/wards/", vhx.hospital_wards_view, name="hospital_wards"),
    path("inpatient/admissions/", vhx.hospital_admissions_view, name="hospital_admissions"),
    path("billing/", vhx.hospital_billing_hub_view, name="hospital_billing"),
    path("billing/insurance-plans/", vhx.hospital_insurance_plans_view, name="hospital_insurance_plans"),
    path("billing/invoices/", vhx.hospital_invoices_view, name="hospital_invoices"),
    path("lab-lines/<int:line_id>/result/", vhx.hospital_lab_line_result_view, name="hospital_lab_line_result"),
]
