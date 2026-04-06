from __future__ import annotations

from datetime import date, datetime, time

from django.contrib import messages
from django.db import transaction
from django.db import models
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from rbac.models import user_has_permission
from tenant_portal.auth import get_tenant_db_for_request
from tenant_portal.decorators import tenant_view
from tenant_portal.url_utils import reverse_tenant
from tenant_hospital.services.mrn import next_mrn


def _require_perm_or_redirect(
    request: HttpRequest,
    tenant_db: str,
    perm_code: str,
    *,
    message: str,
    redirect_name: str,
) -> HttpResponse | None:
    user = getattr(request, "tenant_user", None)
    if not user or not user_has_permission(user, perm_code, using=tenant_db):
        messages.error(request, message)
        return redirect(reverse_tenant(request, redirect_name))
    return None


@tenant_view(require_module="hospital", require_perm_any=["module:hospital.view", "module:hospital.manage"])
def hospital_home_view(request: HttpRequest) -> HttpResponse:
    tenant_db = get_tenant_db_for_request(request)
    if not tenant_db:
        return redirect(reverse_tenant(request, "tenant_portal:home"))

    from tenant_hospital.models import Appointment, Patient

    today = timezone.localdate()
    start = timezone.make_aware(datetime.combine(today, time.min))
    end = timezone.make_aware(datetime.combine(today, time.max))
    ctx = {
        "tenant": getattr(request, "tenant", None),
        "tenant_user": getattr(request, "tenant_user", None),
        "patient_count": Patient.objects.using(tenant_db).filter(is_active=True).count(),
        "appointments_today": Appointment.objects.using(tenant_db).filter(start_at__gte=start, start_at__lte=end).count(),
    }
    return render(request, "tenant_portal/hospital/home.html", ctx)


@tenant_view(require_module="hospital", require_perm_any=["module:hospital.view", "module:hospital.manage"])
@require_http_methods(["GET", "POST"])
def hospital_departments_view(request: HttpRequest) -> HttpResponse:
    tenant_db = get_tenant_db_for_request(request)
    if not tenant_db:
        return redirect(reverse_tenant(request, "tenant_portal:home"))
    deny = _require_perm_or_redirect(
        request,
        tenant_db,
        "module:hospital.manage",
        message="You do not have permission to manage hospital master data.",
        redirect_name="tenant_portal:hospital_home",
    )
    if deny:
        return deny

    from tenant_hospital.models import Department

    if request.method == "POST":
        code = (request.POST.get("code") or "").strip().upper()
        name = (request.POST.get("name") or "").strip()
        if not code or not name:
            messages.error(request, "Department code and name are required.")
        else:
            Department.objects.using(tenant_db).update_or_create(
                code=code,
                defaults={"name": name, "is_active": True},
            )
            messages.success(request, f"Department saved: {code}.")
            return redirect(reverse_tenant(request, "tenant_portal:hospital_departments"))

    departments = list(Department.objects.using(tenant_db).order_by("code"))
    return render(
        request,
        "tenant_portal/hospital/departments.html",
        {
            "tenant": getattr(request, "tenant", None),
            "tenant_user": getattr(request, "tenant_user", None),
            "departments": departments,
        },
    )


@tenant_view(require_module="hospital", require_perm_any=["module:hospital.view", "module:hospital.manage"])
@require_http_methods(["GET", "POST"])
def hospital_providers_view(request: HttpRequest) -> HttpResponse:
    tenant_db = get_tenant_db_for_request(request)
    if not tenant_db:
        return redirect(reverse_tenant(request, "tenant_portal:home"))
    deny = _require_perm_or_redirect(
        request,
        tenant_db,
        "module:hospital.manage",
        message="You do not have permission to manage hospital master data.",
        redirect_name="tenant_portal:hospital_home",
    )
    if deny:
        return deny

    from tenant_hospital.models import Department, Provider

    departments = list(Department.objects.using(tenant_db).filter(is_active=True).order_by("code"))

    if request.method == "POST":
        full_name = (request.POST.get("full_name") or "").strip()
        provider_type = (request.POST.get("provider_type") or Provider.ProviderType.PHYSICIAN).strip()
        dept_id = request.POST.get("department_id")
        license_number = (request.POST.get("license_number") or "").strip()
        phone = (request.POST.get("phone") or "").strip()
        email = (request.POST.get("email") or "").strip()

        if not full_name:
            messages.error(request, "Provider name is required.")
        else:
            dept_fk = None
            if dept_id:
                try:
                    dept_id_int = int(dept_id)
                except (TypeError, ValueError):
                    dept_id_int = None
                if dept_id_int:
                    dept_fk = (
                        Department.objects.using(tenant_db)
                        .filter(pk=dept_id_int, is_active=True)
                        .first()
                    )
            Provider.objects.using(tenant_db).create(
                full_name=full_name,
                provider_type=provider_type if provider_type in Provider.ProviderType.values else Provider.ProviderType.OTHER,
                department=dept_fk,
                license_number=license_number,
                phone=phone,
                email=email,
                is_active=True,
            )
            messages.success(request, "Provider created.")
            return redirect(reverse_tenant(request, "tenant_portal:hospital_providers"))

    providers = list(
        Provider.objects.using(tenant_db)
        .select_related("department")
        .order_by("full_name", "id")
    )
    return render(
        request,
        "tenant_portal/hospital/providers.html",
        {
            "tenant": getattr(request, "tenant", None),
            "tenant_user": getattr(request, "tenant_user", None),
            "providers": providers,
            "departments": departments,
            "provider_type_choices": Provider.ProviderType.choices,
        },
    )


@tenant_view(require_module="hospital", require_perm_any=["module:hospital.view", "module:hospital.manage"])
@require_http_methods(["GET"])
def hospital_patients_view(request: HttpRequest) -> HttpResponse:
    tenant_db = get_tenant_db_for_request(request)
    if not tenant_db:
        return redirect(reverse_tenant(request, "tenant_portal:home"))
    user = getattr(request, "tenant_user", None)
    if not user or not user_has_permission(user, "hospital:patients.view", using=tenant_db):
        messages.error(request, "You do not have permission to view patients.")
        return redirect(reverse_tenant(request, "tenant_portal:hospital_home"))

    q = (request.GET.get("q") or "").strip()
    from tenant_hospital.models import Patient

    qs = Patient.objects.using(tenant_db).all().order_by("full_name", "mrn")
    if q:
        qs = qs.filter(models.Q(full_name__icontains=q) | models.Q(mrn__icontains=q))
    patients = list(qs[:200])
    return render(
        request,
        "tenant_portal/hospital/patients.html",
        {
            "tenant": getattr(request, "tenant", None),
            "tenant_user": getattr(request, "tenant_user", None),
            "patients": patients,
            "q": q,
        },
    )


@tenant_view(require_module="hospital", require_perm_any=["module:hospital.view", "module:hospital.manage"])
@require_http_methods(["GET", "POST"])
def hospital_patient_create_view(request: HttpRequest) -> HttpResponse:
    tenant_db = get_tenant_db_for_request(request)
    if not tenant_db:
        return redirect(reverse_tenant(request, "tenant_portal:home"))
    user = getattr(request, "tenant_user", None)
    if not user or not user_has_permission(user, "hospital:patients.manage", using=tenant_db):
        messages.error(request, "You do not have permission to create patients.")
        return redirect(reverse_tenant(request, "tenant_portal:hospital_patients"))

    from tenant_hospital.models import Patient

    if request.method == "POST":
        full_name = (request.POST.get("full_name") or "").strip()
        phone = (request.POST.get("phone") or "").strip()
        email = (request.POST.get("email") or "").strip()
        gender = (request.POST.get("gender") or Patient.Gender.UNKNOWN).strip()
        address = (request.POST.get("address") or "").strip()
        allergies = (request.POST.get("allergies") or "").strip()
        emergency_contact_name = (request.POST.get("emergency_contact_name") or "").strip()
        emergency_contact_phone = (request.POST.get("emergency_contact_phone") or "").strip()
        dob_raw = (request.POST.get("date_of_birth") or "").strip()
        date_of_birth = None
        if dob_raw:
            try:
                date_of_birth = date.fromisoformat(dob_raw)
            except ValueError:
                date_of_birth = None
        if not full_name:
            messages.error(request, "Full name is required.")
        else:
            with transaction.atomic(using=tenant_db):
                mrn = next_mrn(using=tenant_db)
                p = Patient.objects.using(tenant_db).create(
                    mrn=mrn,
                    full_name=full_name,
                    phone=phone,
                    email=email,
                    gender=gender if gender in Patient.Gender.values else Patient.Gender.UNKNOWN,
                    date_of_birth=date_of_birth,
                    address=address,
                    allergies=allergies,
                    emergency_contact_name=emergency_contact_name,
                    emergency_contact_phone=emergency_contact_phone,
                )
            messages.success(request, f"Patient created: {p.full_name} ({p.mrn}).")
            return redirect(reverse_tenant(request, "tenant_portal:hospital_patients"))

    return render(
        request,
        "tenant_portal/hospital/patient_create.html",
        {
            "tenant": getattr(request, "tenant", None),
            "tenant_user": getattr(request, "tenant_user", None),
            "gender_choices": Patient.Gender.choices,
        },
    )


def _parse_dt_local(value: str, tz) -> datetime | None:
    """
    Parse an <input type="datetime-local"> value.
    Returns timezone-aware datetime in current timezone.
    """
    s = (value or "").strip()
    if not s:
        return None
    try:
        # Expected "YYYY-MM-DDTHH:MM" (seconds optional)
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone=tz)
    return timezone.localtime(dt, timezone=tz)


@tenant_view(require_module="hospital", require_perm_any=["module:hospital.view", "module:hospital.manage"])
@require_http_methods(["GET"])
def hospital_appointments_view(request: HttpRequest) -> HttpResponse:
    tenant_db = get_tenant_db_for_request(request)
    if not tenant_db:
        return redirect(reverse_tenant(request, "tenant_portal:home"))
    deny = _require_perm_or_redirect(
        request,
        tenant_db,
        "hospital:appointments.view",
        message="You do not have permission to view appointments.",
        redirect_name="tenant_portal:hospital_home",
    )
    if deny:
        return deny

    from tenant_hospital.models import Appointment

    day = (request.GET.get("day") or "").strip()
    tz = timezone.get_current_timezone()
    day_date = None
    if day:
        try:
            day_date = datetime.fromisoformat(day).date()
        except ValueError:
            day_date = None

    qs = (
        Appointment.objects.using(tenant_db)
        .select_related("patient", "provider", "department", "encounter")
        .order_by("-start_at", "id")
    )
    if day_date:
        start = timezone.make_aware(datetime.combine(day_date, time.min), timezone=tz)
        end = timezone.make_aware(datetime.combine(day_date, time.max), timezone=tz)
        qs = qs.filter(start_at__gte=start, start_at__lte=end)

    appts = list(qs[:300])
    return render(
        request,
        "tenant_portal/hospital/appointments.html",
        {
            "tenant": getattr(request, "tenant", None),
            "tenant_user": getattr(request, "tenant_user", None),
            "appointments": appts,
            "day": day,
        },
    )


@tenant_view(require_module="hospital", require_perm_any=["module:hospital.view", "module:hospital.manage"])
@require_http_methods(["GET", "POST"])
def hospital_appointment_create_view(request: HttpRequest) -> HttpResponse:
    tenant_db = get_tenant_db_for_request(request)
    if not tenant_db:
        return redirect(reverse_tenant(request, "tenant_portal:home"))
    deny = _require_perm_or_redirect(
        request,
        tenant_db,
        "hospital:appointments.manage",
        message="You do not have permission to create appointments.",
        redirect_name="tenant_portal:hospital_appointments",
    )
    if deny:
        return deny

    from tenant_hospital.models import Appointment, Department, Patient, Provider

    tz = timezone.get_current_timezone()
    patients = list(Patient.objects.using(tenant_db).filter(is_active=True).order_by("full_name", "mrn")[:500])
    providers = list(Provider.objects.using(tenant_db).filter(is_active=True).order_by("full_name")[:500])
    departments = list(Department.objects.using(tenant_db).filter(is_active=True).order_by("code"))

    if request.method == "POST":
        patient_id = request.POST.get("patient_id")
        provider_id = request.POST.get("provider_id")
        department_id = request.POST.get("department_id")
        start_at = _parse_dt_local(request.POST.get("start_at") or "", tz)
        end_at = _parse_dt_local(request.POST.get("end_at") or "", tz)
        reason = (request.POST.get("reason") or "").strip()

        patient = None
        try:
            patient = Patient.objects.using(tenant_db).filter(pk=int(patient_id)).first() if patient_id else None
        except (TypeError, ValueError):
            patient = None

        provider = None
        try:
            provider = Provider.objects.using(tenant_db).filter(pk=int(provider_id), is_active=True).first() if provider_id else None
        except (TypeError, ValueError):
            provider = None

        department = None
        try:
            department = Department.objects.using(tenant_db).filter(pk=int(department_id), is_active=True).first() if department_id else None
        except (TypeError, ValueError):
            department = None

        if not patient:
            messages.error(request, "Patient is required.")
        elif not start_at or not end_at:
            messages.error(request, "Start and end time are required.")
        elif end_at <= start_at:
            messages.error(request, "End time must be after start time.")
        else:
            # Basic overlap check per provider (if provider selected).
            if provider:
                overlap = (
                    Appointment.objects.using(tenant_db)
                    .filter(provider=provider)
                    .exclude(status__in=[Appointment.Status.CANCELLED, Appointment.Status.NO_SHOW])
                    .filter(start_at__lt=end_at, end_at__gt=start_at)
                    .exists()
                )
                if overlap:
                    messages.error(request, "This provider already has an overlapping appointment in that time range.")
                    return render(
                        request,
                        "tenant_portal/hospital/appointment_create.html",
                        {
                            "tenant": getattr(request, "tenant", None),
                            "tenant_user": getattr(request, "tenant_user", None),
                            "patients": patients,
                            "providers": providers,
                            "departments": departments,
                            "default_start_at": (request.POST.get("start_at") or ""),
                            "default_end_at": (request.POST.get("end_at") or ""),
                            "default_reason": reason,
                            "default_patient_id": patient_id or "",
                            "default_provider_id": provider_id or "",
                            "default_department_id": department_id or "",
                        },
                    )

            with transaction.atomic(using=tenant_db):
                Appointment.objects.using(tenant_db).create(
                    patient=patient,
                    provider=provider,
                    department=department,
                    start_at=start_at,
                    end_at=end_at,
                    reason=reason,
                    status=Appointment.Status.SCHEDULED,
                )
            messages.success(request, "Appointment scheduled.")
            return redirect(reverse_tenant(request, "tenant_portal:hospital_appointments"))

    return render(
        request,
        "tenant_portal/hospital/appointment_create.html",
        {
            "tenant": getattr(request, "tenant", None),
            "tenant_user": getattr(request, "tenant_user", None),
            "patients": patients,
            "providers": providers,
            "departments": departments,
            "default_start_at": "",
            "default_end_at": "",
            "default_reason": "",
            "default_patient_id": "",
            "default_provider_id": "",
            "default_department_id": "",
        },
    )


@tenant_view(require_module="hospital", require_perm_any=["module:hospital.view", "module:hospital.manage"])
@require_http_methods(["GET", "POST"])
def hospital_encounter_create_view(request: HttpRequest, appointment_id: int) -> HttpResponse:
    tenant_db = get_tenant_db_for_request(request)
    if not tenant_db:
        return redirect(reverse_tenant(request, "tenant_portal:home"))
    deny = _require_perm_or_redirect(
        request,
        tenant_db,
        "hospital:encounters.manage",
        message="You do not have permission to create encounters.",
        redirect_name="tenant_portal:hospital_appointments",
    )
    if deny:
        return deny

    from tenant_hospital.models import Appointment, Encounter, OutpatientVisit

    appt = (
        Appointment.objects.using(tenant_db)
        .select_related("patient", "provider", "department")
        .filter(pk=appointment_id)
        .first()
    )
    if not appt:
        messages.error(request, "Appointment not found.")
        return redirect(reverse_tenant(request, "tenant_portal:hospital_appointments"))

    existing = Encounter.objects.using(tenant_db).filter(appointment=appt).first()
    if existing:
        messages.info(request, "This appointment already has an encounter.")
        return redirect(
            reverse_tenant(request, "tenant_portal:hospital_encounter_detail", kwargs={"encounter_id": existing.pk})
        )

    if request.method == "POST":
        chief = (request.POST.get("chief_complaint") or "").strip()
        summary = (request.POST.get("summary") or "").strip()
        started_at = timezone.now()
        with transaction.atomic(using=tenant_db):
            from tenant_hospital.models import Encounter as EncModel, OutpatientVisit

            enc = EncModel.objects.using(tenant_db).create(
                patient=appt.patient,
                provider=appt.provider,
                appointment=appt,
                visit_kind=EncModel.VisitKind.OPD,
                started_at=started_at,
                chief_complaint=chief,
                summary=summary,
            )
            OutpatientVisit.objects.using(tenant_db).create(
                encounter=enc,
                visit_date=timezone.localdate(appt.start_at),
                department=appt.department,
                doctor=appt.provider,
            )
            if appt.status == Appointment.Status.SCHEDULED:
                appt.status = Appointment.Status.COMPLETED
                appt.save(using=tenant_db, update_fields=["status"])
        enc = Encounter.objects.using(tenant_db).filter(appointment=appt).first()
        messages.success(request, "Encounter created.")
        if enc:
            return redirect(
                reverse_tenant(request, "tenant_portal:hospital_encounter_detail", kwargs={"encounter_id": enc.pk})
            )
        return redirect(reverse_tenant(request, "tenant_portal:hospital_appointments"))

    return render(
        request,
        "tenant_portal/hospital/encounter_create.html",
        {
            "tenant": getattr(request, "tenant", None),
            "tenant_user": getattr(request, "tenant_user", None),
            "appointment": appt,
        },
    )


@tenant_view(require_module="hospital", require_perm_any=["module:hospital.view", "module:hospital.manage"])
@require_http_methods(["GET"])
def hospital_patient_detail_view(request: HttpRequest, patient_id: int) -> HttpResponse:
    tenant_db = get_tenant_db_for_request(request)
    if not tenant_db:
        return redirect(reverse_tenant(request, "tenant_portal:home"))
    user = getattr(request, "tenant_user", None)
    if not user or not user_has_permission(user, "hospital:patients.view", using=tenant_db):
        messages.error(request, "You do not have permission to view this patient.")
        return redirect(reverse_tenant(request, "tenant_portal:hospital_patients"))

    from tenant_hospital.models import (
        Admission,
        EmergencyVisit,
        OutpatientVisit,
        Patient,
        PatientDocument,
        PatientInsurance,
        PatientInvoice,
    )

    patient = Patient.objects.using(tenant_db).filter(pk=patient_id).first()
    if not patient:
        messages.error(request, "Patient not found.")
        return redirect(reverse_tenant(request, "tenant_portal:hospital_patients"))

    opd_visits = list(
        OutpatientVisit.objects.using(tenant_db)
        .filter(encounter__patient_id=patient.pk)
        .select_related("encounter", "department", "doctor")
        .order_by("-visit_date", "-id")[:100]
    )
    er_visits = list(
        EmergencyVisit.objects.using(tenant_db)
        .filter(encounter__patient_id=patient.pk)
        .select_related("encounter")
        .order_by("-encounter__started_at")[:100]
    )
    admissions = list(
        Admission.objects.using(tenant_db)
        .filter(patient_id=patient.pk)
        .select_related("bed", "bed__ward", "attending_provider", "encounter")
        .order_by("-admitted_at")[:100]
    )
    from tenant_hospital.models import LabOrder

    lab_orders = list(
        LabOrder.objects.using(tenant_db).filter(patient_id=patient.pk).order_by("-ordered_at")[:100]
    )
    invoices = list(
        PatientInvoice.objects.using(tenant_db).filter(patient_id=patient.pk).order_by("-issued_at")[:100]
    )
    insurance = list(
        PatientInsurance.objects.using(tenant_db).filter(patient_id=patient.pk).select_related("plan")[:20]
    )
    documents = list(
        PatientDocument.objects.using(tenant_db).filter(patient_id=patient.pk).order_by("-uploaded_at")[:50]
    )

    can_manage = bool(user and user_has_permission(user, "hospital:patients.manage", using=tenant_db))

    return render(
        request,
        "tenant_portal/hospital/patient_detail.html",
        {
            "tenant": getattr(request, "tenant", None),
            "tenant_user": getattr(request, "tenant_user", None),
            "patient": patient,
            "opd_visits": opd_visits,
            "er_visits": er_visits,
            "admissions": admissions,
            "lab_orders": lab_orders,
            "invoices": invoices,
            "insurance": insurance,
            "documents": documents,
            "can_manage_patient": can_manage,
        },
    )


@tenant_view(require_module="hospital", require_perm_any=["module:hospital.view", "module:hospital.manage"])
@require_http_methods(["GET"])
def hospital_opd_list_view(request: HttpRequest) -> HttpResponse:
    tenant_db = get_tenant_db_for_request(request)
    if not tenant_db:
        return redirect(reverse_tenant(request, "tenant_portal:home"))
    user = getattr(request, "tenant_user", None)
    if not user or not user_has_permission(user, "hospital:patients.view", using=tenant_db):
        messages.error(request, "You do not have permission to view OPD visits.")
        return redirect(reverse_tenant(request, "tenant_portal:hospital_home"))

    from tenant_hospital.models import OutpatientVisit

    visits = list(
        OutpatientVisit.objects.using(tenant_db)
        .select_related("encounter", "encounter__patient", "department", "doctor")
        .order_by("-visit_date", "-id")[:300]
    )
    return render(
        request,
        "tenant_portal/hospital/opd_list.html",
        {
            "tenant": getattr(request, "tenant", None),
            "tenant_user": getattr(request, "tenant_user", None),
            "visits": visits,
        },
    )


@tenant_view(require_module="hospital", require_perm_any=["module:hospital.view", "module:hospital.manage"])
@require_http_methods(["GET", "POST"])
def hospital_opd_visit_create_view(request: HttpRequest) -> HttpResponse:
    tenant_db = get_tenant_db_for_request(request)
    if not tenant_db:
        return redirect(reverse_tenant(request, "tenant_portal:home"))
    user = getattr(request, "tenant_user", None)
    if not user or not user_has_permission(user, "hospital:patients.manage", using=tenant_db):
        messages.error(request, "You do not have permission to register OPD visits.")
        return redirect(reverse_tenant(request, "tenant_portal:hospital_opd_list"))

    from tenant_hospital.models import Department, Encounter, OutpatientVisit, Patient, Provider

    patients = list(Patient.objects.using(tenant_db).filter(is_active=True).order_by("full_name", "mrn")[:800])
    providers = list(Provider.objects.using(tenant_db).filter(is_active=True).order_by("full_name")[:500])
    departments = list(Department.objects.using(tenant_db).filter(is_active=True).order_by("code"))

    if request.method == "POST":
        pid = request.POST.get("patient_id")
        visit_date_raw = (request.POST.get("visit_date") or "").strip()
        dept_id = request.POST.get("department_id")
        doc_id = request.POST.get("doctor_id")
        symptoms = (request.POST.get("symptoms") or "").strip()
        diagnosis = (request.POST.get("diagnosis") or "").strip()
        prescription = (request.POST.get("prescription") or "").strip()
        fu_raw = (request.POST.get("follow_up_date") or "").strip()

        patient = None
        try:
            patient = Patient.objects.using(tenant_db).filter(pk=int(pid), is_active=True).first() if pid else None
        except (TypeError, ValueError):
            patient = None

        visit_date = None
        if visit_date_raw:
            try:
                visit_date = date.fromisoformat(visit_date_raw)
            except ValueError:
                visit_date = None

        doctor = None
        try:
            doctor = Provider.objects.using(tenant_db).filter(pk=int(doc_id), is_active=True).first() if doc_id else None
        except (TypeError, ValueError):
            doctor = None

        department = None
        try:
            department = Department.objects.using(tenant_db).filter(pk=int(dept_id), is_active=True).first() if dept_id else None
        except (TypeError, ValueError):
            department = None

        follow_up_date = None
        if fu_raw:
            try:
                follow_up_date = date.fromisoformat(fu_raw)
            except ValueError:
                follow_up_date = None

        if not patient or not visit_date:
            messages.error(request, "Patient and visit date are required.")
        else:
            tz = timezone.get_current_timezone()
            started = timezone.make_aware(datetime.combine(visit_date, time(9, 0)), timezone=tz)
            with transaction.atomic(using=tenant_db):
                enc = Encounter.objects.using(tenant_db).create(
                    patient=patient,
                    provider=doctor,
                    visit_kind=Encounter.VisitKind.OPD,
                    started_at=started,
                    chief_complaint=(symptoms[:255] if symptoms else ""),
                )
                OutpatientVisit.objects.using(tenant_db).create(
                    encounter=enc,
                    visit_date=visit_date,
                    department=department,
                    doctor=doctor,
                    symptoms=symptoms,
                    diagnosis=diagnosis,
                    prescription=prescription,
                    follow_up_date=follow_up_date,
                )
            messages.success(request, f"OPD visit recorded for {patient.full_name} ({patient.mrn}).")
            return redirect(reverse_tenant(request, "tenant_portal:hospital_opd_list"))

    return render(
        request,
        "tenant_portal/hospital/opd_visit_create.html",
        {
            "tenant": getattr(request, "tenant", None),
            "tenant_user": getattr(request, "tenant_user", None),
            "patients": patients,
            "providers": providers,
            "departments": departments,
        },
    )


@tenant_view(require_module="hospital", require_perm_any=["module:hospital.view", "module:hospital.manage"])
@require_http_methods(["GET"])
def hospital_emergency_list_view(request: HttpRequest) -> HttpResponse:
    tenant_db = get_tenant_db_for_request(request)
    if not tenant_db:
        return redirect(reverse_tenant(request, "tenant_portal:home"))
    user = getattr(request, "tenant_user", None)
    if not user or not user_has_permission(user, "hospital:patients.view", using=tenant_db):
        messages.error(request, "You do not have permission to view emergency visits.")
        return redirect(reverse_tenant(request, "tenant_portal:hospital_home"))

    from tenant_hospital.models import EmergencyVisit

    visits = list(
        EmergencyVisit.objects.using(tenant_db)
        .select_related("encounter", "encounter__patient")
        .order_by("-encounter__started_at")[:300]
    )
    return render(
        request,
        "tenant_portal/hospital/emergency_list.html",
        {
            "tenant": getattr(request, "tenant", None),
            "tenant_user": getattr(request, "tenant_user", None),
            "visits": visits,
        },
    )


@tenant_view(require_module="hospital", require_perm_any=["module:hospital.view", "module:hospital.manage"])
@require_http_methods(["GET", "POST"])
def hospital_emergency_visit_create_view(request: HttpRequest) -> HttpResponse:
    tenant_db = get_tenant_db_for_request(request)
    if not tenant_db:
        return redirect(reverse_tenant(request, "tenant_portal:home"))
    user = getattr(request, "tenant_user", None)
    if not user or not user_has_permission(user, "hospital:patients.manage", using=tenant_db):
        messages.error(request, "You do not have permission to register emergency visits.")
        return redirect(reverse_tenant(request, "tenant_portal:hospital_emergency_list"))

    from tenant_hospital.models import EmergencyVisit, Encounter, Patient

    patients = list(Patient.objects.using(tenant_db).filter(is_active=True).order_by("full_name", "mrn")[:800])
    tz = timezone.get_current_timezone()

    if request.method == "POST":
        pid = request.POST.get("patient_id")
        arrival_raw = (request.POST.get("arrival_at") or "").strip()
        triage = (request.POST.get("triage_level") or "").strip()
        notes = (request.POST.get("emergency_notes") or "").strip()
        outcome = (request.POST.get("outcome") or EmergencyVisit.Outcome.DISCHARGE).strip()

        patient = None
        try:
            patient = Patient.objects.using(tenant_db).filter(pk=int(pid), is_active=True).first() if pid else None
        except (TypeError, ValueError):
            patient = None

        arrival = _parse_dt_local(arrival_raw, tz) if arrival_raw else timezone.now()

        if not patient:
            messages.error(request, "Patient is required.")
        else:
            _outcomes = {c[0] for c in EmergencyVisit.Outcome.choices}
            if outcome not in _outcomes:
                outcome = EmergencyVisit.Outcome.DISCHARGE
            with transaction.atomic(using=tenant_db):
                enc = Encounter.objects.using(tenant_db).create(
                    patient=patient,
                    visit_kind=Encounter.VisitKind.EMERGENCY,
                    started_at=arrival,
                )
                EmergencyVisit.objects.using(tenant_db).create(
                    encounter=enc,
                    triage_level=triage[:40],
                    emergency_notes=notes,
                    outcome=outcome,
                )
            messages.success(request, f"Emergency visit recorded for {patient.full_name} ({patient.mrn}).")
            return redirect(reverse_tenant(request, "tenant_portal:hospital_emergency_list"))

    return render(
        request,
        "tenant_portal/hospital/emergency_visit_create.html",
        {
            "tenant": getattr(request, "tenant", None),
            "tenant_user": getattr(request, "tenant_user", None),
            "patients": patients,
            "outcome_choices": EmergencyVisit.Outcome.choices,
        },
    )


@tenant_view(require_module="hospital", require_perm_any=["module:hospital.view", "module:hospital.manage"])
def hospital_setup_hub_view(request: HttpRequest) -> HttpResponse:
    """Master data and configuration entry points for Hospital Management."""
    tenant_db = get_tenant_db_for_request(request)
    if not tenant_db:
        return redirect(reverse_tenant(request, "tenant_portal:home"))

    return render(
        request,
        "tenant_portal/hospital/setup_hub.html",
        {
            "tenant": getattr(request, "tenant", None),
            "tenant_user": getattr(request, "tenant_user", None),
        },
    )

