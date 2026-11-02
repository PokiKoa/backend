from datetime import time
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from audit.models import AuditAction, AuditLog
from patients.models import DischargeOutcome
from patients.services import admit_patient, discharge_patient
from poki_koa.exceptions import (
    ConflictDomainError,
    DomainError,
    PermissionDomainError,
)

from .models import AdministrationRoute, PrescriptionStatus
from .services import (
    administer_prescription,
    cancel_prescription,
    create_catalog_item,
    create_prescription,
    update_catalog_item,
)


class MedicationsServiceTests(TestCase):
    def setUp(self) -> None:
        self.admin = User.objects.create_user(
            email="admin_med@pokikoa.cl",
            full_name="Admin Medicación",
            password="Str0ng!Password2026",
            role=UserRole.ADMIN,
        )
        self.neo = User.objects.create_user(
            email="neo_med@pokikoa.cl",
            full_name="Neonatóloga Medicación",
            password="Str0ng!Password2026",
            role=UserRole.NEONATOLOGIST,
        )
        self.nurse = User.objects.create_user(
            email="nurse_med@pokikoa.cl",
            full_name="Enfermera Medicación",
            password="Str0ng!Password2026",
            role=UserRole.NURSE,
        )
        self.pharmacist = User.objects.create_user(
            email="pharm_med@pokikoa.cl",
            full_name="Farmacéutico Medicación",
            password="Str0ng!Password2026",
            role=UserRole.PHARMACIST,
        )
        self.patient = admit_patient(
            actor=self.neo,
            medical_record_number="RN-MED-01",
            full_name="RN Farmacoterapia",
            sex="F",
            birth_date=timezone.localdate(),
            gestational_age_weeks=Decimal("31.5"),
            birth_weight_g=1520,
        )

    def test_catalog_boundaries_equivalences_and_rbac(self) -> None:
        # Enfermera y Neonatólogo no pueden crear ítems en catálogo
        with self.assertRaises(PermissionDomainError):
            create_catalog_item(
                actor=self.nurse,
                name="Cafeína Citrato",
                active_ingredient="Cafeína",
                concentration_mg=Decimal("20.00"),
                stock=10,
            )

        # Límite inferior válido: concentration_mg = 0.01 y stock = 0
        item = create_catalog_item(
            actor=self.pharmacist,
            name="Surfactante Pulmonar",
            active_ingredient="Beractant",
            concentration_mg=Decimal("0.01"),
            unit="vial",
            stock=0,
            min_stock_alert=3,
        )
        self.assertEqual(item.stock, 0)
        self.assertTrue(item.is_low_stock)

        # Equivalencias inválidas: concentración <= 0 o stock < 0 o duplicado
        with self.assertRaises(DomainError):
            create_catalog_item(
                actor=self.pharmacist,
                name="Inválido Cero",
                active_ingredient="Activo",
                concentration_mg=Decimal("0.00"),
            )

        with self.assertRaises(DomainError):
            create_catalog_item(
                actor=self.pharmacist,
                name="Inválido Stock",
                active_ingredient="Activo",
                concentration_mg=Decimal("10.00"),
                stock=-1,
            )

        with self.assertRaises(ConflictDomainError):
            create_catalog_item(
                actor=self.pharmacist,
                name="surfactante pulmonar",
                active_ingredient="Beractant",
                concentration_mg=Decimal("25.00"),
            )

    def test_prescription_atomic_administration_last_unit_and_no_double_admin(self) -> None:
        caffeine = create_catalog_item(
            actor=self.pharmacist,
            name="Cafeína Citrato 20mg/ml",
            active_ingredient="Citrato de Cafeína",
            concentration_mg=Decimal("20.00"),
            unit="ampolla",
            stock=1,
            min_stock_alert=2,
        )

        # Enfermera no puede prescribir indicaciones médicas
        with self.assertRaises(PermissionDomainError):
            create_prescription(
                actor=self.nurse,
                patient_id=self.patient.id,
                medication_id=caffeine.id,
                dose="10 mg IV cada 24h",
                scheduled_time=time(8, 0),
            )

        p1 = create_prescription(
            actor=self.neo,
            patient_id=self.patient.id,
            medication_id=caffeine.id,
            dose="10 mg IV",
            scheduled_time=time(8, 0),
            route=AdministrationRoute.IV,
            units_per_administration=1,
        )
        p2 = create_prescription(
            actor=self.neo,
            patient_id=self.patient.id,
            medication_id=caffeine.id,
            dose="10 mg IV",
            scheduled_time=time(20, 0),
            route=AdministrationRoute.IV,
            units_per_administration=1,
        )

        # Farmacéutico no puede administrar al paciente
        with self.assertRaises(PermissionDomainError):
            administer_prescription(actor=self.pharmacist, prescription=p1)

        # Enfermera administra la última unidad en stock (1 -> 0 sin fallar)
        administered = administer_prescription(
            actor=self.nurse,
            prescription=p1,
            notes="Administrado por vía venosa central sin incidentes.",
        )
        self.assertEqual(administered.status, PrescriptionStatus.ADMINISTERED)
        self.assertEqual(administered.administered_by_id, self.nurse.id)
        caffeine.refresh_from_db()
        self.assertEqual(caffeine.stock, 0)

        # Rechazo de doble administración sobre p1 (409 ConflictDomainError)
        with self.assertRaises(ConflictDomainError):
            administer_prescription(actor=self.nurse, prescription=p1)

        # Rechazo atómico de p2 cuando el stock es 0 (no permite stock negativo)
        with self.assertRaises(ConflictDomainError):
            administer_prescription(actor=self.nurse, prescription=p2)
        p2.refresh_from_db()
        self.assertEqual(p2.status, PrescriptionStatus.PENDING)
        caffeine.refresh_from_db()
        self.assertEqual(caffeine.stock, 0)

        # Al egresar al paciente, las prescripciones pendientes se cancelan automáticamente
        discharge_patient(
            actor=self.neo,
            patient=self.patient,
            outcome=DischargeOutcome.SURVIVED,
        )
        p2.refresh_from_db()
        self.assertEqual(p2.status, PrescriptionStatus.CANCELLED)


class MedicationsEndpointTests(APITestCase):
    def setUp(self) -> None:
        self.admin = User.objects.create_user(
            email="admin_mep@pokikoa.cl",
            full_name="Admin Med EP",
            password="Str0ng!Password2026",
            role=UserRole.ADMIN,
        )
        self.neo = User.objects.create_user(
            email="neo_mep@pokikoa.cl",
            full_name="Neonatólogo Med EP",
            password="Str0ng!Password2026",
            role=UserRole.NEONATOLOGIST,
        )
        self.nurse = User.objects.create_user(
            email="nurse_mep@pokikoa.cl",
            full_name="Enfermera Med EP",
            password="Str0ng!Password2026",
            role=UserRole.NURSE,
        )
        self.pharmacist = User.objects.create_user(
            email="pharm_mep@pokikoa.cl",
            full_name="Farmacéutico Med EP",
            password="Str0ng!Password2026",
            role=UserRole.PHARMACIST,
        )
        self.patient = admit_patient(
            actor=self.neo,
            medical_record_number="RN-MEP-01",
            full_name="RN Endpoint Medicación",
            sex="M",
            birth_date=timezone.localdate(),
            gestational_age_weeks=Decimal("33.0"),
            birth_weight_g=1850,
        )

    def test_medication_catalog_and_prescription_endpoints_full_flow(self) -> None:
        # Enfermera no puede dar de alta medicamentos en catálogo (403)
        self.client.force_authenticate(user=self.nurse)
        forbidden_cat = self.client.post(
            "/api/v1/medication-catalog/",
            {
                "name": "Ampicilina 500mg",
                "active_ingredient": "Ampicilina Sódica",
                "concentration_mg": "500.00",
                "unit": "frasco-ampolla",
                "stock": 2,
            },
            format="json",
        )
        self.assertEqual(forbidden_cat.status_code, status.HTTP_403_FORBIDDEN)

        # Farmacéutico crea medicamento en el catálogo (201)
        self.client.force_authenticate(user=self.pharmacist)
        cat_res = self.client.post(
            "/api/v1/medication-catalog/",
            {
                "name": "Ampicilina 500mg",
                "active_ingredient": "Ampicilina Sódica",
                "concentration_mg": "500.00",
                "unit": "frasco-ampolla",
                "stock": 2,
                "min_stock_alert": 5,
            },
            format="json",
        )
        self.assertEqual(cat_res.status_code, status.HTTP_201_CREATED)
        med_id = cat_res.data["id"]
        self.assertTrue(cat_res.data["is_low_stock"])

        # Neonatólogo prescribe dos dosis para el paciente
        self.client.force_authenticate(user=self.neo)
        presc1 = self.client.post(
            "/api/v1/prescriptions/",
            {
                "patient_id": self.patient.id,
                "medication_id": med_id,
                "dose": "90 mg IV lento",
                "units_per_administration": 1,
                "route": "IV",
                "scheduled_time": "09:00:00",
            },
            format="json",
        )
        self.assertEqual(presc1.status_code, status.HTTP_201_CREATED)
        p1_id = presc1.data["id"]

        presc2 = self.client.post(
            "/api/v1/prescriptions/",
            {
                "patient_id": self.patient.id,
                "medication_id": med_id,
                "dose": "90 mg IV lento",
                "units_per_administration": 1,
                "route": "IV",
                "scheduled_time": "21:00:00",
            },
            format="json",
        )
        p2_id = presc2.data["id"]

        # Enfermera administra la primera indicación (stock pasa de 2 a 1)
        self.client.force_authenticate(user=self.nurse)
        adm_res = self.client.post(
            f"/api/v1/prescriptions/{p1_id}/administer/",
            {"notes": "Dosis matinal administrada."},
            format="json",
        )
        self.assertEqual(adm_res.status_code, status.HTTP_200_OK)
        self.assertEqual(adm_res.data["status"], PrescriptionStatus.ADMINISTERED)

        # Intentar doble administración por API devuelve 409 Conflict
        dup_adm = self.client.post(
            f"/api/v1/prescriptions/{p1_id}/administer/",
            {},
            format="json",
        )
        self.assertEqual(dup_adm.status_code, status.HTTP_409_CONFLICT)

        # Verificar descuento de stock en catálogo (stock == 1)
        cat_get = self.client.get(f"/api/v1/medication-catalog/{med_id}/")
        self.assertEqual(cat_get.data["stock"], 1)

        # Neonatólogo cancela la segunda indicación pendiente
        self.client.force_authenticate(user=self.neo)
        cancel_res = self.client.post(
            f"/api/v1/prescriptions/{p2_id}/cancel/",
            {"reason": "Ajuste de esquema antibiótico según hemocultivo."},
            format="json",
        )
        self.assertEqual(cancel_res.status_code, status.HTTP_200_OK)
        self.assertEqual(cancel_res.data["status"], PrescriptionStatus.CANCELLED)

        # Farmacéutico repone stock mediante update_catalog_item / PATCH
        self.client.force_authenticate(user=self.pharmacist)
        patch_res = self.client.patch(
            f"/api/v1/medication-catalog/{med_id}/",
            {"stock": 25},
            format="json",
        )
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_res.data["stock"], 25)
        self.assertFalse(patch_res.data["is_low_stock"])

        # Verificar también actualización por servicio directo
        item_obj = update_catalog_item(
            actor=self.admin,
            item=cancel_res.renderer_context["view"].get_object().medication,
            data={"min_stock_alert": 10},
        )
        self.assertEqual(item_obj.min_stock_alert, 10)

        with self.assertRaises(ConflictDomainError):
            cancel_prescription(
                actor=self.neo,
                prescription=cancel_res.renderer_context["view"].get_object(),
            )

        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditAction.ADMINISTER_MEDICATION,
                patient_id=self.patient.id,
            ).exists()
        )
