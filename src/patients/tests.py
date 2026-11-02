from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from audit.models import AuditAction, AuditLog
from devices.models import CribStatus
from devices.services import create_crib
from poki_koa.exceptions import (
    ConflictDomainError,
    DomainError,
    PermissionDomainError,
)

from .models import (
    CarePlanStatus,
    DischargeCause,
    DischargeOutcome,
    ObservationCategory,
    Patient,
    PatientStatus,
)
from .services import (
    admit_patient,
    create_care_plan,
    create_clinical_observation,
    discharge_patient,
    record_patient_weight,
    update_patient,
)


class PatientsServiceTests(TestCase):
    def setUp(self) -> None:
        self.admin = User.objects.create_user(
            email="admin_p@pokikoa.cl",
            full_name="Admin Pacientes",
            password="Str0ng!Password2026",
            role=UserRole.ADMIN,
        )
        self.neo = User.objects.create_user(
            email="neo_p@pokikoa.cl",
            full_name="Camila Rojas",
            password="Str0ng!Password2026",
            role=UserRole.NEONATOLOGIST,
        )
        self.nurse = User.objects.create_user(
            email="nurse_p@pokikoa.cl",
            full_name="Enfermera Pacientes",
            password="Str0ng!Password2026",
            role=UserRole.NURSE,
        )
        self.pharmacist = User.objects.create_user(
            email="pharm_p@pokikoa.cl",
            full_name="Farmacéutico Pacientes",
            password="Str0ng!Password2026",
            role=UserRole.PHARMACIST,
        )
        self.crib, _ = create_crib(actor=self.admin, code="C-301", name="Cuna UCI 301")

    def test_admit_patient_boundary_values_and_equivalences(self) -> None:
        today = timezone.localdate()

        # Caso límite inferior válido: 20.0 semanas y 200 g
        p_min = admit_patient(
            actor=self.neo,
            medical_record_number="rn-min-200",
            full_name="RN Límite Inferior",
            sex="F",
            birth_date=today,
            gestational_age_weeks=Decimal("20.0"),
            birth_weight_g=200,
        )
        self.assertEqual(p_min.medical_record_number, "RN-MIN-200")
        self.assertEqual(p_min.current_weight_g, 200)
        self.assertEqual(p_min.weight_records.count(), 1)

        # Caso límite superior válido: 45.0 semanas y 8000 g (peso actual 10000 g)
        p_max = admit_patient(
            actor=self.nurse,
            medical_record_number="RN-MAX-8000",
            full_name="RN Límite Superior",
            sex="M",
            birth_date=today,
            gestational_age_weeks=Decimal("45.0"),
            birth_weight_g=8000,
            current_weight_g=10000,
        )
        self.assertEqual(p_max.current_weight_g, 10000)

        # Equivalencias inválidas: fuera de límites fisiológicos
        with self.assertRaises(DomainError):
            admit_patient(
                actor=self.neo,
                medical_record_number="RN-INV-1",
                full_name="RN Inválido",
                sex="F",
                birth_date=today,
                gestational_age_weeks=Decimal("19.9"),
                birth_weight_g=1500,
            )

        with self.assertRaises(DomainError):
            admit_patient(
                actor=self.neo,
                medical_record_number="RN-INV-2",
                full_name="RN Inválido",
                sex="F",
                birth_date=today,
                gestational_age_weeks=Decimal("45.1"),
                birth_weight_g=1500,
            )

        with self.assertRaises(DomainError):
            admit_patient(
                actor=self.neo,
                medical_record_number="RN-INV-3",
                full_name="RN Inválido",
                sex="F",
                birth_date=today,
                gestational_age_weeks=Decimal("32.0"),
                birth_weight_g=199,
            )

        with self.assertRaises(DomainError):
            admit_patient(
                actor=self.neo,
                medical_record_number="RN-INV-4",
                full_name="RN Inválido",
                sex="F",
                birth_date=today + timedelta(days=1),
                gestational_age_weeks=Decimal("32.0"),
                birth_weight_g=1500,
            )

        # Ficha duplicada rechazada atómicamente
        with self.assertRaises(ConflictDomainError):
            admit_patient(
                actor=self.neo,
                medical_record_number="rn-min-200",
                full_name="Duplicado",
                sex="M",
                birth_date=today,
                gestational_age_weeks=Decimal("35.0"),
                birth_weight_g=2200,
            )

        # Médico tratante debe ser Neonatólogo
        with self.assertRaises(DomainError):
            admit_patient(
                actor=self.neo,
                medical_record_number="RN-INV-PHYS",
                full_name="Médico Inválido",
                sex="M",
                birth_date=today,
                gestational_age_weeks=Decimal("35.0"),
                birth_weight_g=2200,
                attending_physician_id=self.nurse.id,
            )

    def test_weight_record_deduplication_and_curve_update(self) -> None:
        patient = admit_patient(
            actor=self.neo,
            medical_record_number="RN-WEIGHT-01",
            full_name="RN Curva Ponderal",
            sex="F",
            birth_date=timezone.localdate(),
            gestational_age_weeks=Decimal("31.0"),
            birth_weight_g=1450,
        )
        self.assertEqual(patient.weight_records.count(), 1)

        # Registrar el mismo peso consecutivo no duplica la fila (regla IncuNest)
        dup_record = record_patient_weight(
            actor=self.nurse,
            patient=patient,
            weight_g=1450,
        )
        self.assertEqual(patient.weight_records.count(), 1)
        self.assertEqual(dup_record.weight_g, 1450)

        # Registrar un nuevo peso agrega punto y actualiza current_weight_g
        new_record = record_patient_weight(
            actor=self.nurse,
            patient=patient,
            weight_g=1495,
        )
        patient.refresh_from_db()
        self.assertEqual(patient.weight_records.count(), 2)
        self.assertEqual(patient.current_weight_g, 1495)
        self.assertEqual(new_record.weight_g, 1495)

    def test_field_level_rbac_and_logical_discharge(self) -> None:
        patient = admit_patient(
            actor=self.neo,
            medical_record_number="RN-DISC-01",
            full_name="RN Ciclo Completo",
            sex="M",
            birth_date=timezone.localdate() - timedelta(days=5),
            gestational_age_weeks=Decimal("29.5"),
            birth_weight_g=1250,
            attending_physician_id=self.neo.id,
            crib_id=self.crib.id,
        )
        self.crib.refresh_from_db()
        self.assertEqual(self.crib.status, CribStatus.OCCUPIED)

        # Plan de cuidado activo antes del egreso
        plan = create_care_plan(
            actor=self.nurse,
            patient_id=patient.id,
            care_area="Termorregulación",
            intervention="Control servocontrolado de temperatura cutánea",
            frequency="Cada 3 horas",
        )
        obs = create_clinical_observation(
            actor=self.nurse,
            patient_id=patient.id,
            category=ObservationCategory.KANGAROO_CARE,
            content="Toleró sesión de método canguro por 60 minutos sin apneas.",
        )
        self.assertEqual(obs.category, ObservationCategory.KANGAROO_CARE)

        # Enfermera puede actualizar peso pero NO diagnóstico ni médico tratante
        with self.assertRaises(PermissionDomainError):
            update_patient(
                actor=self.nurse,
                patient=patient,
                data={"diagnosis": "SDR neonatal"},
            )

        update_patient(
            actor=self.neo,
            patient=patient,
            data={"diagnosis": "SDR neonatal en resolución"},
        )

        # Enfermera no puede firmar egreso
        with self.assertRaises(PermissionDomainError):
            discharge_patient(
                actor=self.nurse,
                patient=patient,
                outcome=DischargeOutcome.SURVIVED,
            )

        # Egreso por fallecimiento exige causa distinta de 'none'
        with self.assertRaises(DomainError):
            discharge_patient(
                actor=self.neo,
                patient=patient,
                outcome=DischargeOutcome.DECEASED,
                cause=DischargeCause.NONE,
            )

        # Neonatólogo firma egreso domiciliario
        discharged = discharge_patient(
            actor=self.neo,
            patient=patient,
            outcome=DischargeOutcome.SURVIVED,
            cause=DischargeCause.PREMATURITY,
            notes="Alta con seguimiento en policlínico de prematuros.",
        )
        self.assertEqual(discharged.status, PatientStatus.DISCHARGED)
        self.assertIsNone(discharged.crib)
        self.assertIsNotNone(discharged.discharged_at)

        self.crib.refresh_from_db()
        self.assertEqual(self.crib.status, CribStatus.AVAILABLE)

        plan.refresh_from_db()
        self.assertEqual(plan.status, CarePlanStatus.COMPLETED)

        # Paciente egresado queda protegido contra ediciones ulteriores
        with self.assertRaises(ConflictDomainError):
            update_patient(
                actor=self.neo,
                patient=discharged,
                data={"current_weight_g": 1300},
            )


class PatientsEndpointTests(APITestCase):
    def setUp(self) -> None:
        self.admin = User.objects.create_user(
            email="admin_ep@pokikoa.cl",
            full_name="Admin Endpoint",
            password="Str0ng!Password2026",
            role=UserRole.ADMIN,
        )
        self.neo = User.objects.create_user(
            email="neo_ep@pokikoa.cl",
            full_name="Diego Soto",
            password="Str0ng!Password2026",
            role=UserRole.NEONATOLOGIST,
        )
        self.nurse = User.objects.create_user(
            email="nurse_ep@pokikoa.cl",
            full_name="Enfermera Endpoint",
            password="Str0ng!Password2026",
            role=UserRole.NURSE,
        )
        self.pharmacist = User.objects.create_user(
            email="pharm_ep@pokikoa.cl",
            full_name="Farmacéutico Endpoint",
            password="Str0ng!Password2026",
            role=UserRole.PHARMACIST,
        )
        self.crib, _ = create_crib(actor=self.admin, code="C-401", name="Cuna 401")

    def test_patient_endpoints_rbac_delete_405_audit_and_subresources(self) -> None:
        today_str = str(timezone.localdate())

        # Farmacéutico no puede crear pacientes (403)
        self.client.force_authenticate(user=self.pharmacist)
        pharm_post = self.client.post(
            "/api/v1/patients/",
            {
                "medical_record_number": "RN-4001",
                "full_name": "RN Farmacia",
                "sex": "F",
                "birth_date": today_str,
                "gestational_age_weeks": "36.0",
                "birth_weight_g": 2600,
            },
            format="json",
        )
        self.assertEqual(pharm_post.status_code, status.HTTP_403_FORBIDDEN)

        # Neonatólogo admite paciente con cuna y médico asignados
        self.client.force_authenticate(user=self.neo)
        create_res = self.client.post(
            "/api/v1/patients/",
            {
                "medical_record_number": "RN-4001",
                "full_name": "RN Martín González",
                "sex": "M",
                "birth_date": today_str,
                "gestational_age_weeks": "33.5",
                "birth_weight_g": 1980,
                "diagnosis": "Prematuridad moderada",
                "attending_physician_id": self.neo.id,
                "crib_id": self.crib.id,
            },
            format="json",
        )
        self.assertEqual(create_res.status_code, status.HTTP_201_CREATED)
        patient_id = create_res.data["id"]
        self.assertEqual(create_res.data["crib_code"], "C-401")
        self.assertEqual(create_res.data["attending_physician_name"], "Diego Soto")

        # DELETE físico está prohibido (405 Method Not Allowed)
        del_res = self.client.delete(f"/api/v1/patients/{patient_id}/")
        self.assertEqual(del_res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(Patient.objects.filter(pk=patient_id).exists())

        # Retrieve registra evento de lectura en AuditLog
        get_res = self.client.get(f"/api/v1/patients/{patient_id}/")
        self.assertEqual(get_res.status_code, status.HTTP_200_OK)
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditAction.READ,
                resource_type="patient",
                patient_id=patient_id,
            ).exists()
        )

        # Enfermera registra peso y consulta curva ponderal
        self.client.force_authenticate(user=self.nurse)
        w_post = self.client.post(
            f"/api/v1/patients/{patient_id}/weights/",
            {"weight_g": 2030},
            format="json",
        )
        self.assertEqual(w_post.status_code, status.HTTP_201_CREATED)

        w_list = self.client.get(f"/api/v1/patients/{patient_id}/weights/")
        self.assertEqual(w_list.status_code, status.HTTP_200_OK)
        self.assertEqual(w_list.data["count"], 2)

        # Crear y actualizar plan de cuidado por API
        cp_post = self.client.post(
            "/api/v1/care-plans/",
            {
                "patient_id": patient_id,
                "care_area": "Nutrición enteral",
                "intervention": "Lactancia materna fortificada 20 ml por sonda",
                "frequency": "Cada 3 horas",
            },
            format="json",
        )
        self.assertEqual(cp_post.status_code, status.HTTP_201_CREATED)
        cp_id = cp_post.data["id"]

        cp_patch = self.client.patch(
            f"/api/v1/care-plans/{cp_id}/",
            {"frequency": "Cada 2 horas"},
            format="json",
        )
        self.assertEqual(cp_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(cp_patch.data["frequency"], "Cada 2 horas")

        # Crear y filtrar observación clínica por API
        obs_post = self.client.post(
            "/api/v1/observations/",
            {
                "patient_id": patient_id,
                "category": ObservationCategory.NURSING,
                "content": "Control de signos vitales dentro de rangos esperados.",
            },
            format="json",
        )
        self.assertEqual(obs_post.status_code, status.HTTP_201_CREATED)

        obs_list = self.client.get(
            f"/api/v1/observations/?patient={patient_id}&category=nursing"
        )
        self.assertEqual(obs_list.status_code, status.HTTP_200_OK)
        self.assertEqual(obs_list.data["count"], 1)

        # Egreso lógico por endpoint
        self.client.force_authenticate(user=self.neo)
        disc_res = self.client.post(
            f"/api/v1/patients/{patient_id}/discharge/",
            {
                "outcome": DischargeOutcome.SURVIVED,
                "cause": DischargeCause.PREMATURITY,
                "notes": "Egreso en buenas condiciones generales.",
            },
            format="json",
        )
        self.assertEqual(disc_res.status_code, status.HTTP_200_OK)
        self.assertEqual(disc_res.data["status"], PatientStatus.DISCHARGED)
        self.assertIsNone(disc_res.data["crib"])
