"""
Hospital module: EMR (vitals, notes), lab, pharmacy, inpatient, billing.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from rbac.models import user_has_permission
from tenant_hospital.services.billing_numbers import next_invoice_number
from tenant_hospital.services.order_numbers import next_lab_order_number, next_pharmacy_order_number
from tenant_portal.auth import get_tenant_db_for_request
from tenant_portal.decorators import tenant_view
from tenant_portal.url_utils import reverse_tenant
from tenant_portal.views_hospital import _require_perm_or_redirect


def _has_star_or_perm(request: HttpRequest, code: str, tenant_db: str) -> bool:
    u = getattr(request, "tenant_user", None)
    if not u:
        return False
    cached = getattr(request, "rbac_permission_codes", None)
    if isinstance(cached, set) and ("*" in cached or code in cached):
        return True
    return user_has_permission(u, code, using=tenant_db)


def _ctx(request: HttpRequest) -> dict:
    return {
        "tenant": getattr(request, "tenant", None),
        "tenant_user": getattr(request, "tenant_user", None),
    }


@tenant_view(require_module="hospital", require_perm_any=["module:hospital.view", "module:hospital.manage"])
@require_http_methods(["GET"])
def hospital_encounter_detail_view(request: HttpRequest, encounter_id: int) -> HttpResponse:
    tenant_db = get_tenant_db_for_request(request)
    if not tenant_db:
        return redirect(reverse_tenant(request, "tenant_portal:home"))
    deny = _require_perm_or_redirect(
        request,
        tenant_db,
        "hospital:emr.view",
        message="You do not have permission to view the clinical chart.",
        redirect_name="tenant_portal:hospital_home",
    )
    if deny:
        return deny

    from tenant_hospital.models import ClinicalNote, Encounter, LabOrder, PharmacyOrder, Provider, VitalSign

    enc = get_object_or_404(
        Encounter.objects.using(tenant_db).select_related("patient", "provider", "appointment"),
        pk=encounter_id,
    )
    vitals = list(
        VitalSign.objects.using(tenant_db).filter(encounter=enc).order_by("-recorded_at")[:50]
    )
    notes = list(
        ClinicalNote.objects.using(tenant_db)
        .filter(encounter=enc)
        .select_related("author_provider")
        .order_by("-created_at")[:50]
    )
    lab_orders = list(
        LabOrder.objects.using(tenant_db).filter(encounter=enc).prefetch_related("lines").order_by("-ordered_at")
    )
    rx_orders = list(
        PharmacyOrder.objects.using(tenant_db).filter(encounter=enc).prefetch_related("lines").order_by("-ordered_at")
    )
    providers = list(Provider.objects.using(tenant_db).filter(is_active=True).order_by("full_name")[:300])
    tu = getattr(request, "tenant_user", None)
    can_manage_emr = bool(tu and _has_star_or_perm(request, "hospital:emr.manage", tenant_db))
    can_lab = bool(tu and _has_star_or_perm(request, "hospital:lab.manage", tenant_db))
    can_rx = bool(tu and _has_star_or_perm(request, "hospital:pharmacy.manage", tenant_db))

    return render(
        request,
        "tenant_portal/hospital/encounter_detail.html",
        {
            **_ctx(request),
            "encounter": enc,
            "vitals": vitals,
            "clinical_notes": notes,
            "lab_orders": lab_orders,
            "pharmacy_orders": rx_orders,
            "providers": providers,
            "note_type_choices": ClinicalNote.NoteType.choices,
            "can_manage_emr": can_manage_emr,
            "can_lab_manage": can_lab,
            "can_pharmacy_manage": can_rx,
        },
    )


@tenant_view(require_module="hospital", require_perm_any=["module:hospital.view", "module:hospital.manage"])
@require_http_methods(["POST"])
def hospital_encounter_vital_add_view(request: HttpRequest, encounter_id: int) -> HttpResponse:
    tenant_db = get_tenant_db_for_request(request)
    if not tenant_db:
        return redirect(reverse_tenant(request, "tenant_portal:home"))
    deny = _require_perm_or_redirect(
        request,
        tenant_db,
        "hospital:emr.manage",
        message="You do not have permission to record vitals.",
        redirect_name="tenant_portal:hospital_home",
    )
    if deny:
        return deny

    from tenant_hospital.models import Encounter, VitalSign

    enc = get_object_or_404(Encounter.objects.using(tenant_db), pk=encounter_id)

    def _int(name: str):
        v = (request.POST.get(name) or "").strip()
        if not v:
            return None
        try:
            return int(v)
        except ValueError:
            return None

    def _dec(name: str):
        v = (request.POST.get(name) or "").strip()
        if not v:
            return None
        try:
            return Decimal(v)
        except (InvalidOperation, ValueError):
            return None

    bp_s = _int("bp_systolic")
    bp_d = _int("bp_diastolic")
    hr = _int("heart_rate")
    temp = _dec("temperature_c")
    spo2 = _int("spo2")
    rr = _int("respiratory_rate")
    w = _dec("weight_kg")
    h = _dec("height_cm")
    vn = (request.POST.get("notes") or "").strip()[:255]
    if not any([bp_s, bp_d, hr, temp, spo2, rr, w, h, vn]):
        messages.error(request, "Enter at least one vital sign or a note.")
        return redirect(reverse_tenant(request, "tenant_portal:hospital_encounter_detail", kwargs={"encounter_id": enc.pk}))

    VitalSign.objects.using(tenant_db).create(
        encounter=enc,
        recorded_at=timezone.now(),
        bp_systolic=bp_s,
        bp_diastolic=bp_d,
        heart_rate=hr,
        temperature_c=temp,
        spo2=spo2,
        respiratory_rate=rr,
        weight_kg=w,
        height_cm=h,
        notes=vn,
    )
    messages.success(request, "Vitals saved.")
    return redirect(reverse_tenant(request, "tenant_portal:hospital_encounter_detail", kwargs={"encounter_id": enc.pk}))


@tenant_view(require_module="hospital", require_perm_any=["module:hospital.view", "module:hospital.manage"])
@require_http_methods(["POST"])
def hospital_encounter_note_add_view(request: HttpRequest, encounter_id: int) -> HttpResponse:
    tenant_db = get_tenant_db_for_request(request)
    if not tenant_db:
        return redirect(reverse_tenant(request, "tenant_portal:home"))
    deny = _require_perm_or_redirect(
        request,
        tenant_db,
        "hospital:emr.manage",
        message="You do not have permission to add clinical notes.",
        redirect_name="tenant_portal:hospital_home",
    )
    if deny:
        return deny

    from tenant_hospital.models import ClinicalNote, Encounter, Provider

    enc = get_object_or_404(Encounter.objects.using(tenant_db), pk=encounter_id)
    body = (request.POST.get("body") or "").strip()
    nt = (request.POST.get("note_type") or ClinicalNote.NoteType.PROGRESS).strip()
    pid = request.POST.get("author_provider_id")
    author = None
    if pid:
        try:
            author = Provider.objects.using(tenant_db).filter(pk=int(pid), is_active=True).first()
        except (TypeError, ValueError):
            author = None
    if not body:
        messages.error(request, "Note text is required.")
    else:
        ClinicalNote.objects.using(tenant_db).create(
            encounter=enc,
            author_provider=author,
            note_type=nt if nt in ClinicalNote.NoteType.values else ClinicalNote.NoteType.PROGRESS,
            body=body,
        )
        messages.success(request, "Note added.")
    return redirect(reverse_tenant(request, "tenant_portal:hospital_encounter_detail", kwargs={"encounter_id": enc.pk}))


@tenant_view(require_module="hospital", require_perm_any=["module:hospital.view", "module:hospital.manage"])
@require_http_methods(["POST"])
def hospital_encounter_lab_order_add_view(request: HttpRequest, encounter_id: int) -> HttpResponse:
    tenant_db = get_tenant_db_for_request(request)
    if not tenant_db:
        return redirect(reverse_tenant(request, "tenant_portal:home"))
    deny = _require_perm_or_redirect(
        request,
        tenant_db,
        "hospital:lab.manage",
        message="You do not have permission to order labs.",
        redirect_name="tenant_portal:hospital_home",
    )
    if deny:
        return deny

    from tenant_hospital.models import Encounter, LabOrder, LabOrderLine, Provider

    enc = get_object_or_404(Encounter.objects.using(tenant_db), pk=encounter_id)
    test_name = (request.POST.get("test_name") or "").strip()
    test_code = (request.POST.get("test_code") or "").strip()
    pid = request.POST.get("ordered_by_id")
    ordered_by = None
    if pid:
        try:
            ordered_by = Provider.objects.using(tenant_db).filter(pk=int(pid), is_active=True).first()
        except (TypeError, ValueError):
            ordered_by = None
    if not test_name:
        messages.error(request, "Test name is required.")
        return redirect(reverse_tenant(request, "tenant_portal:hospital_encounter_detail", kwargs={"encounter_id": enc.pk}))

    with transaction.atomic(using=tenant_db):
        num = next_lab_order_number(using=tenant_db)
        lo = LabOrder.objects.using(tenant_db).create(
            order_number=num,
            patient=enc.patient,
            encounter=enc,
            ordered_by=ordered_by,
            status=LabOrder.Status.ORDERED,
            ordered_at=timezone.now(),
        )
        LabOrderLine.objects.using(tenant_db).create(
            lab_order=lo,
            test_code=test_code,
            test_name=test_name,
            status=LabOrderLine.LineStatus.PENDING,
        )
    messages.success(request, f"Lab order {num} created.")
    return redirect(reverse_tenant(request, "tenant_portal:hospital_encounter_detail", kwargs={"encounter_id": enc.pk}))


@tenant_view(require_module="hospital", require_perm_any=["module:hospital.view", "module:hospital.manage"])
@require_http_methods(["POST"])
def hospital_encounter_rx_order_add_view(request: HttpRequest, encounter_id: int) -> HttpResponse:
    tenant_db = get_tenant_db_for_request(request)
    if not tenant_db:
        return redirect(reverse_tenant(request, "tenant_portal:home"))
    deny = _require_perm_or_redirect(
        request,
        tenant_db,
        "hospital:pharmacy.manage",
        message="You do not have permission to order medications.",
        redirect_name="tenant_portal:hospital_home",
    )
    if deny:
        return deny

    from tenant_hospital.models import Encounter, PharmacyOrder, PharmacyOrderLine, Provider

    enc = get_object_or_404(Encounter.objects.using(tenant_db), pk=encounter_id)
    med = (request.POST.get("medication_name") or "").strip()
    pid = request.POST.get("ordered_by_id")
    ordered_by = None
    if pid:
        try:
            ordered_by = Provider.objects.using(tenant_db).filter(pk=int(pid), is_active=True).first()
        except (TypeError, ValueError):
            ordered_by = None
    if not med:
        messages.error(request, "Medication name is required.")
        return redirect(reverse_tenant(request, "tenant_portal:hospital_encounter_detail", kwargs={"encounter_id": enc.pk}))

    with transaction.atomic(using=tenant_db):
        num = next_pharmacy_order_number(using=tenant_db)
        po = PharmacyOrder.objects.using(tenant_db).create(
            order_number=num,
            patient=enc.patient,
            encounter=enc,
            ordered_by=ordered_by,
            status=PharmacyOrder.Status.ORDERED,
            ordered_at=timezone.now(),
        )
        PharmacyOrderLine.objects.using(tenant_db).create(
            pharmacy_order=po,
            medication_name=med,
            dose=(request.POST.get("dose") or "").strip(),
            route=(request.POST.get("route") or "").strip(),
            frequency=(request.POST.get("frequency") or "").strip(),
            quantity=(request.POST.get("quantity") or "").strip(),
            instructions=(request.POST.get("instructions") or "").strip(),
        )
    messages.success(request, f"Pharmacy order {num} created.")
    return redirect(reverse_tenant(request, "tenant_portal:hospital_encounter_detail", kwargs={"encounter_id": enc.pk}))


@tenant_view(require_module="hospital", require_perm_any=["module:hospital.view", "module:hospital.manage"])
@require_http_methods(["GET"])
def hospital_lab_orders_view(request: HttpRequest) -> HttpResponse:
    tenant_db = get_tenant_db_for_request(request)
    if not tenant_db:
        return redirect(reverse_tenant(request, "tenant_portal:home"))
    deny = _require_perm_or_redirect(
        request,
        tenant_db,
        "hospital:lab.view",
        message="You do not have permission to view lab orders.",
        redirect_name="tenant_portal:hospital_home",
    )
    if deny:
        return deny

    from tenant_hospital.models import LabOrder

    orders = list(
        LabOrder.objects.using(tenant_db)
        .select_related("patient", "encounter")
        .prefetch_related("lines")
        .order_by("-ordered_at")[:200]
    )
    can_manage_lab = _has_star_or_perm(request, "hospital:lab.manage", tenant_db)
    return render(
        request,
        "tenant_portal/hospital/lab_orders.html",
        {**_ctx(request), "lab_orders": orders, "can_manage_lab": can_manage_lab},
    )


@tenant_view(require_module="hospital", require_perm_any=["module:hospital.view", "module:hospital.manage"])
@require_http_methods(["GET"])
def hospital_pharmacy_orders_view(request: HttpRequest) -> HttpResponse:
    tenant_db = get_tenant_db_for_request(request)
    if not tenant_db:
        return redirect(reverse_tenant(request, "tenant_portal:home"))
    deny = _require_perm_or_redirect(
        request,
        tenant_db,
        "hospital:pharmacy.view",
        message="You do not have permission to view pharmacy orders.",
        redirect_name="tenant_portal:hospital_home",
    )
    if deny:
        return deny

    from tenant_hospital.models import PharmacyOrder

    orders = list(
        PharmacyOrder.objects.using(tenant_db)
        .select_related("patient", "encounter")
        .prefetch_related("lines")
        .order_by("-ordered_at")[:200]
    )
    return render(request, "tenant_portal/hospital/pharmacy_orders.html", {**_ctx(request), "pharmacy_orders": orders})


@tenant_view(require_module="hospital", require_perm_any=["module:hospital.view", "module:hospital.manage"])
@require_http_methods(["GET", "POST"])
def hospital_wards_view(request: HttpRequest) -> HttpResponse:
    tenant_db = get_tenant_db_for_request(request)
    if not tenant_db:
        return redirect(reverse_tenant(request, "tenant_portal:home"))
    deny = _require_perm_or_redirect(
        request,
        tenant_db,
        "hospital:inpatient.manage",
        message="You do not have permission to manage wards and beds.",
        redirect_name="tenant_portal:hospital_home",
    )
    if deny:
        return deny

    from tenant_hospital.models import Bed, Ward

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if action == "add_ward":
            code = (request.POST.get("ward_code") or "").strip().upper()
            name = (request.POST.get("ward_name") or "").strip()
            floor = (request.POST.get("floor") or "").strip()
            if code and name:
                Ward.objects.using(tenant_db).update_or_create(
                    code=code,
                    defaults={"name": name, "floor": floor, "is_active": True},
                )
                messages.success(request, f"Ward {code} saved.")
            else:
                messages.error(request, "Ward code and name are required.")
        elif action == "add_bed":
            wid = request.POST.get("ward_id")
            room = (request.POST.get("room_label") or "").strip()
            bed = (request.POST.get("bed_label") or "").strip()
            try:
                w = Ward.objects.using(tenant_db).get(pk=int(wid))
            except (TypeError, ValueError, Ward.DoesNotExist):
                messages.error(request, "Invalid ward.")
                return redirect(reverse_tenant(request, "tenant_portal:hospital_wards"))
            if bed:
                Bed.objects.using(tenant_db).get_or_create(
                    ward=w,
                    room_label=room,
                    bed_label=bed,
                    defaults={"status": Bed.Status.AVAILABLE},
                )
                messages.success(request, "Bed added.")
            else:
                messages.error(request, "Bed label is required.")
        return redirect(reverse_tenant(request, "tenant_portal:hospital_wards"))

    wards = list(Ward.objects.using(tenant_db).filter(is_active=True).prefetch_related("beds").order_by("code"))
    return render(request, "tenant_portal/hospital/wards.html", {**_ctx(request), "wards": wards})


@tenant_view(require_module="hospital", require_perm_any=["module:hospital.view", "module:hospital.manage"])
@require_http_methods(["GET", "POST"])
def hospital_admissions_view(request: HttpRequest) -> HttpResponse:
    tenant_db = get_tenant_db_for_request(request)
    if not tenant_db:
        return redirect(reverse_tenant(request, "tenant_portal:home"))
    deny = _require_perm_or_redirect(
        request,
        tenant_db,
        "hospital:inpatient.view",
        message="You do not have permission to view admissions.",
        redirect_name="tenant_portal:hospital_home",
    )
    if deny:
        return deny

    from tenant_hospital.models import Admission, Bed, Encounter, Patient, Provider

    if request.method == "POST" and _has_star_or_perm(request, "hospital:inpatient.manage", tenant_db):
        action = (request.POST.get("action") or "").strip()
        if action == "admit":
            pid = request.POST.get("patient_id")
            bid = request.POST.get("bed_id")
            complaint = (request.POST.get("chief_complaint") or "").strip()
            adm_dx = (request.POST.get("admission_diagnosis") or "").strip()
            att_id = (request.POST.get("attending_provider_id") or "").strip()
            try:
                patient = Patient.objects.using(tenant_db).get(pk=int(pid))
                bed_id_int = int(bid)
            except (TypeError, ValueError, Patient.DoesNotExist):
                messages.error(request, "Invalid patient or bed.")
                return redirect(reverse_tenant(request, "tenant_portal:hospital_admissions"))
            if Admission.objects.using(tenant_db).filter(patient=patient, status=Admission.Status.ACTIVE).exists():
                messages.error(request, "Patient already has an active admission.")
                return redirect(reverse_tenant(request, "tenant_portal:hospital_admissions"))
            attending = None
            if att_id:
                try:
                    attending = Provider.objects.using(tenant_db).filter(pk=int(att_id), is_active=True).first()
                except (TypeError, ValueError):
                    attending = None
            now = timezone.now()
            with transaction.atomic(using=tenant_db):
                bed_locked = Bed.objects.using(tenant_db).select_for_update().filter(pk=bed_id_int).first()
                if not bed_locked or bed_locked.status != Bed.Status.AVAILABLE:
                    messages.error(request, "Bed is not available.")
                    return redirect(reverse_tenant(request, "tenant_portal:hospital_admissions"))
                enc = Encounter.objects.using(tenant_db).create(
                    patient=patient,
                    provider=attending,
                    visit_kind=Encounter.VisitKind.IPD,
                    started_at=now,
                    chief_complaint=complaint[:255] if complaint else "",
                )
                Admission.objects.using(tenant_db).create(
                    patient=patient,
                    encounter=enc,
                    bed=bed_locked,
                    attending_provider=attending,
                    status=Admission.Status.ACTIVE,
                    admitted_at=now,
                    chief_complaint=complaint,
                    admission_diagnosis=adm_dx,
                )
                bed_locked.status = Bed.Status.OCCUPIED
                bed_locked.save(using=tenant_db, update_fields=["status"])
            messages.success(request, "Patient admitted (single master record; IPD encounter linked).")
            return redirect(reverse_tenant(request, "tenant_portal:hospital_admissions"))
        if action == "discharge":
            aid = request.POST.get("admission_id")
            summary = (request.POST.get("discharge_summary") or "").strip()
            try:
                adm = Admission.objects.using(tenant_db).select_related("bed").get(pk=int(aid), status=Admission.Status.ACTIVE)
            except (TypeError, ValueError, Admission.DoesNotExist):
                messages.error(request, "Admission not found.")
                return redirect(reverse_tenant(request, "tenant_portal:hospital_admissions"))
            with transaction.atomic(using=tenant_db):
                adm.status = Admission.Status.DISCHARGED
                adm.discharged_at = timezone.now()
                adm.discharge_summary = summary
                adm.save(using=tenant_db, update_fields=["status", "discharged_at", "discharge_summary", "updated_at"])
                if adm.encounter_id:
                    Encounter.objects.using(tenant_db).filter(pk=adm.encounter_id).update(
                        ended_at=adm.discharged_at,
                    )
                b = Bed.objects.using(tenant_db).select_for_update().get(pk=adm.bed_id)
                b.status = Bed.Status.AVAILABLE
                b.save(using=tenant_db, update_fields=["status"])
            messages.success(request, "Patient discharged.")
            return redirect(reverse_tenant(request, "tenant_portal:hospital_admissions"))

    active = list(
        Admission.objects.using(tenant_db)
        .filter(status=Admission.Status.ACTIVE)
        .select_related("patient", "bed", "bed__ward", "attending_provider", "encounter")
        .order_by("-admitted_at")
    )
    patients = list(Patient.objects.using(tenant_db).filter(is_active=True).order_by("full_name")[:500])
    providers = list(Provider.objects.using(tenant_db).filter(is_active=True).order_by("full_name")[:500])
    beds = list(
        Bed.objects.using(tenant_db)
        .filter(status=Bed.Status.AVAILABLE)
        .select_related("ward")
        .order_by("ward__code", "room_label", "bed_label")[:500]
    )
    tu = getattr(request, "tenant_user", None)
    can_manage = bool(tu and _has_star_or_perm(request, "hospital:inpatient.manage", tenant_db))
    return render(
        request,
        "tenant_portal/hospital/admissions.html",
        {
            **_ctx(request),
            "admissions": active,
            "patients": patients,
            "beds": beds,
            "providers": providers,
            "can_manage_inpatient": can_manage,
        },
    )


@tenant_view(require_module="hospital", require_perm_any=["module:hospital.view", "module:hospital.manage"])
@require_http_methods(["GET", "POST"])
def hospital_billing_hub_view(request: HttpRequest) -> HttpResponse:
    tenant_db = get_tenant_db_for_request(request)
    if not tenant_db:
        return redirect(reverse_tenant(request, "tenant_portal:home"))
    deny = _require_perm_or_redirect(
        request,
        tenant_db,
        "hospital:billing.view",
        message="You do not have permission to view hospital billing.",
        redirect_name="tenant_portal:hospital_home",
    )
    if deny:
        return deny
    return render(request, "tenant_portal/hospital/billing_hub.html", _ctx(request))


@tenant_view(require_module="hospital", require_perm_any=["module:hospital.view", "module:hospital.manage"])
@require_http_methods(["GET", "POST"])
def hospital_insurance_plans_view(request: HttpRequest) -> HttpResponse:
    tenant_db = get_tenant_db_for_request(request)
    if not tenant_db:
        return redirect(reverse_tenant(request, "tenant_portal:home"))
    deny = _require_perm_or_redirect(
        request,
        tenant_db,
        "hospital:billing.manage",
        message="You do not have permission to manage insurance plans.",
        redirect_name="tenant_portal:hospital_billing",
    )
    if deny:
        return deny

    from tenant_hospital.models import InsurancePlan

    if request.method == "POST":
        code = (request.POST.get("code") or "").strip().upper()
        name = (request.POST.get("name") or "").strip()
        payer = (request.POST.get("payer_name") or "").strip()
        if code and name:
            InsurancePlan.objects.using(tenant_db).update_or_create(
                code=code,
                defaults={"name": name, "payer_name": payer, "is_active": True},
            )
            messages.success(request, "Insurance plan saved.")
        else:
            messages.error(request, "Code and name are required.")
        return redirect(reverse_tenant(request, "tenant_portal:hospital_insurance_plans"))

    plans = list(InsurancePlan.objects.using(tenant_db).order_by("code"))
    return render(request, "tenant_portal/hospital/insurance_plans.html", {**_ctx(request), "plans": plans})


@tenant_view(require_module="hospital", require_perm_any=["module:hospital.view", "module:hospital.manage"])
@require_http_methods(["GET", "POST"])
def hospital_invoices_view(request: HttpRequest) -> HttpResponse:
    tenant_db = get_tenant_db_for_request(request)
    if not tenant_db:
        return redirect(reverse_tenant(request, "tenant_portal:home"))
    deny = _require_perm_or_redirect(
        request,
        tenant_db,
        "hospital:billing.view",
        message="You do not have permission to view invoices.",
        redirect_name="tenant_portal:hospital_home",
    )
    if deny:
        return deny

    from tenant_hospital.models import Encounter, Patient, PatientInvoice

    if request.method == "POST" and _has_star_or_perm(request, "hospital:billing.manage", tenant_db):
        pid = request.POST.get("patient_id")
        eid = (request.POST.get("encounter_id") or "").strip()
        amt = (request.POST.get("total_amount") or "").strip()
        try:
            patient = Patient.objects.using(tenant_db).get(pk=int(pid))
        except (TypeError, ValueError, Patient.DoesNotExist):
            messages.error(request, "Patient is required.")
            return redirect(reverse_tenant(request, "tenant_portal:hospital_invoices"))
        enc = None
        if eid:
            try:
                enc = Encounter.objects.using(tenant_db).filter(pk=int(eid), patient=patient).first()
            except (TypeError, ValueError):
                enc = None
        try:
            total = Decimal(amt or "0")
        except (InvalidOperation, ValueError):
            total = Decimal("0")
        with transaction.atomic(using=tenant_db):
            inv = PatientInvoice.objects.using(tenant_db).create(
                invoice_number=next_invoice_number(using=tenant_db),
                patient=patient,
                encounter=enc,
                status=PatientInvoice.Status.DRAFT,
                total_amount=total,
                issued_at=timezone.now(),
            )
        messages.success(request, f"Invoice {inv.invoice_number} created.")
        return redirect(reverse_tenant(request, "tenant_portal:hospital_invoices"))

    invoices = list(
        PatientInvoice.objects.using(tenant_db)
        .select_related("patient", "encounter")
        .order_by("-issued_at")[:200]
    )
    patients = list(Patient.objects.using(tenant_db).filter(is_active=True).order_by("full_name")[:400])
    tu = getattr(request, "tenant_user", None)
    can_manage = bool(tu and _has_star_or_perm(request, "hospital:billing.manage", tenant_db))
    return render(
        request,
        "tenant_portal/hospital/invoices.html",
        {**_ctx(request), "invoices": invoices, "patients": patients, "can_manage_billing": can_manage},
    )


@tenant_view(require_module="hospital", require_perm_any=["module:hospital.view", "module:hospital.manage"])
@require_http_methods(["POST"])
def hospital_lab_line_result_view(request: HttpRequest, line_id: int) -> HttpResponse:
    tenant_db = get_tenant_db_for_request(request)
    if not tenant_db:
        return redirect(reverse_tenant(request, "tenant_portal:home"))
    deny = _require_perm_or_redirect(
        request,
        tenant_db,
        "hospital:lab.manage",
        message="You do not have permission to enter lab results.",
        redirect_name="tenant_portal:hospital_lab_orders",
    )
    if deny:
        return deny

    from tenant_hospital.models import LabOrderLine

    line = get_object_or_404(LabOrderLine.objects.using(tenant_db).select_related("lab_order"), pk=line_id)
    result = (request.POST.get("result_text") or "").strip()
    line.result_text = result
    line.status = LabOrderLine.LineStatus.RESULTED
    line.resulted_at = timezone.now()
    line.save(
        using=tenant_db,
        update_fields=["result_text", "status", "resulted_at"],
    )
    messages.success(request, "Lab result saved.")
    return redirect(reverse_tenant(request, "tenant_portal:hospital_lab_orders"))
