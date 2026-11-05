from datetime import time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import ShiftAssignment, User, UserRole, WorkShift
from accounts.services import current_shift
from devices.models import Crib
from devices.services import create_crib
from medications.models import AdministrationRoute, MedicationCatalogItem
from medications.services import create_catalog_item, create_prescription
from patients.models import ObservationCategory, Patient
from patients.services import (
    admit_patient,
    create_care_plan,
    create_clinical_observation,
    record_patient_weight,
)
from vitals.services import ingest_telemetry


class Command(BaseCommand):
    help = (
        "Carga datos ficticios de demostración neonatal y asegura el superusuario admin/admin2026."
    )

    def handle(self, *args, **options) -> None:
        admin_user, _ = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@pokikoa.cl",
                "full_name": "Administrador General UCIN",
                "role": UserRole.ADMIN,
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.role = UserRole.ADMIN
        admin_user.set_password("admin2026")
        admin_user.save()

        neo, _ = User.objects.get_or_create(
            username="dr.soto",
            defaults={
                "email": "dr.soto@pokikoa.cl",
                "full_name": "Dr. Martín Soto (Neonatólogo)",
                "role": UserRole.NEONATOLOGIST,
                "shift": WorkShift.MORNING,
                "is_staff": True,
            },
        )
        neo.set_password("Clinica#2026")
        neo.save()

        nurse, _ = User.objects.get_or_create(
            username="matrona.diaz",
            defaults={
                "email": "matrona.diaz@pokikoa.cl",
                "full_name": "Matrona Javiera Díaz",
                "role": UserRole.NURSE,
                "shift": WorkShift.MORNING,
                "is_staff": True,
            },
        )
        nurse.set_password("Clinica#2026")
        nurse.save()

        pharmacist, _ = User.objects.get_or_create(
            username="qf.silva",
            defaults={
                "email": "qf.silva@pokikoa.cl",
                "full_name": "QF. Rodrigo Silva",
                "role": UserRole.PHARMACIST,
                "shift": WorkShift.MORNING,
                "is_staff": True,
            },
        )
        pharmacist.set_password("Clinica#2026")
        pharmacist.save()

        crib_specs = [
            ("C-01", "Incubadora Giraffe UCI-1", "Sector UCI A"),
            ("C-02", "Incubadora Giraffe UCI-2", "Sector UCI A"),
            ("C-03", "Cuna Radiante UTI-1", "Sector UTI B"),
            ("C-04", "Cuna Radiante UTI-2", "Sector UTI B"),
        ]
        cribs: dict[str, Crib] = {}
        for code, name, loc in crib_specs:
            existing = Crib.objects.filter(code=code).first()
            if existing is None:
                existing, _ = create_crib(
                    actor=admin_user,
                    code=code,
                    name=name,
                    location=loc,
                )
            cribs[code] = existing

        # Asignaciones para el día del turno vigente y el siguiente, así "Mis cunas" nunca queda vacío
        shift_day, _ = current_shift()
        for offset in (0, 1):
            for shift in WorkShift.values:
                for code in ("C-01", "C-02"):
                    ShiftAssignment.objects.get_or_create(
                        user=nurse,
                        crib=cribs[code],
                        date=shift_day + timedelta(days=offset),
                        shift=shift,
                        defaults={"created_by": admin_user},
                    )

        today = timezone.localdate()
        if not Patient.objects.filter(medical_record_number="RN-2026-001").exists():
            p1 = admit_patient(
                actor=neo,
                medical_record_number="RN-2026-001",
                full_name="RN Mateo González Rojas (Ficticio)",
                sex="M",
                birth_date=today - timedelta(days=4),
                gestational_age_weeks=Decimal("31.5"),
                birth_weight_g=1480,
                current_weight_g=1510,
                diagnosis="Prematuridad moderada, síndrome de dificultad respiratoria en resolución",
                attending_physician_id=neo.id,
                crib_id=cribs["C-01"].id,
                # RUT y teléfonos ficticios (dígito verificador válido, números de ejemplo)
                guardians={
                    "mother_rut": "16.482.937-5",
                    "mother_first_names": "Camila Andrea",
                    "mother_last_names": "Rojas Muñoz",
                    "mother_phone": "+56 9 5555 0101",
                    "father_rut": "15.739.204-2",
                    "father_first_names": "Felipe Ignacio",
                    "father_last_names": "González Pérez",
                    "father_phone": "+56 9 5555 0102",
                },
            )
            record_patient_weight(actor=nurse, patient=p1, weight_g=1535)
            create_care_plan(
                actor=nurse,
                patient_id=p1.id,
                care_area="Termorregulación",
                intervention="Control servocontrolado de temperatura cutánea en 36.7 °C",
                frequency="Cada 3 horas",
            )
            create_clinical_observation(
                actor=nurse,
                patient_id=p1.id,
                category=ObservationCategory.KANGAROO_CARE,
                content="Sesión de contacto piel con piel de 45 minutos con buena estabilidad hemodinámica.",
            )
            ingest_telemetry(
                crib=cribs["C-01"],
                payload={
                    "heart_rate": 138,
                    "spo2": 97,
                    "temperature": "36.8",
                    "sleep_state": "asleep",
                    "cannula_connected": True,
                    "iv_line_active": True,
                },
                is_device_authenticated=True,
            )

        if not Patient.objects.filter(medical_record_number="RN-2026-002").exists():
            p2 = admit_patient(
                actor=neo,
                medical_record_number="RN-2026-002",
                full_name="RN Sofía Contreras Fuentes (Ficticia)",
                sex="F",
                birth_date=today - timedelta(days=2),
                gestational_age_weeks=Decimal("29.0"),
                birth_weight_g=1190,
                current_weight_g=1210,
                diagnosis="Recién nacida pretérmino extrema en soporte no invasivo CPAP",
                attending_physician_id=neo.id,
                crib_id=cribs["C-02"].id,
                guardians={
                    "mother_rut": "17.205.846-9",
                    "mother_first_names": "Valentina Paz",
                    "mother_last_names": "Contreras Fuentes",
                    "mother_phone": "+56 9 5555 0201",
                },
            )
            create_care_plan(
                actor=neo,
                patient_id=p2.id,
                care_area="Soporte Respiratorio",
                intervention="Vigilar fijación de cánula nasal y saturación objetivo 91-95%",
                frequency="Continuo",
            )
            ingest_telemetry(
                crib=cribs["C-02"],
                payload={
                    "heart_rate": 168,
                    "spo2": 88,
                    "temperature": "36.6",
                    "sleep_state": "awake",
                    "cannula_connected": True,
                    "iv_line_active": True,
                },
                is_device_authenticated=True,
            )

        if not MedicationCatalogItem.objects.filter(name="Cafeína Citrato 20mg/ml").exists():
            caffeine = create_catalog_item(
                actor=pharmacist,
                name="Cafeína Citrato 20mg/ml",
                active_ingredient="Citrato de Cafeína",
                concentration_mg=Decimal("20.00"),
                unit="ampolla",
                stock=14,
                min_stock_alert=5,
            )
            surfactant = create_catalog_item(
                actor=pharmacist,
                name="Surfactante Pulmonar 100mg",
                active_ingredient="Beractant",
                concentration_mg=Decimal("100.00"),
                unit="vial",
                stock=2,
                min_stock_alert=4,
            )
            p1_obj = Patient.objects.filter(medical_record_number="RN-2026-001").first()
            p2_obj = Patient.objects.filter(medical_record_number="RN-2026-002").first()
            if p1_obj:
                create_prescription(
                    actor=neo,
                    patient_id=p1_obj.id,
                    medication_id=caffeine.id,
                    dose="5 mg/kg IV lento",
                    # Mantención cada 24 h desde las 08:00 de hoy
                    starts_at=timezone.make_aware(timezone.datetime.combine(today, time(8, 0))),
                    frequency_hours=24,
                    route=AdministrationRoute.IV,
                    units_per_administration=1,
                )
            if p2_obj:
                create_prescription(
                    actor=neo,
                    patient_id=p2_obj.id,
                    medication_id=surfactant.id,
                    dose="100 mg/kg endotraqueal",
                    # Dosis única dentro de una hora
                    starts_at=timezone.now() + timedelta(hours=1),
                    route=AdministrationRoute.ET,
                    units_per_administration=1,
                )

        self.stdout.write(
            self.style.SUCCESS(
                "Datos ficticios cargados y superusuario 'admin' (clave: 'admin2026') listo."
            )
        )
