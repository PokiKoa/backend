"""Caracteriza las reglas de valores del catálogo compartidas por crear y actualizar."""

from decimal import Decimal

from django.test import TestCase

from accounts.models import User, UserRole
from poki_koa.exceptions import DomainError

from .services import create_catalog_item, update_catalog_item

CONCENTRATION_MSG = "La concentración en miligramos debe ser mayor que cero."
STOCK_MSG = "El stock disponible no puede ser negativo."
MIN_STOCK_MSG = "El umbral de alerta de stock mínimo no puede ser negativo."

INVALID_VALUES = [
    ("concentration_mg", "0", CONCENTRATION_MSG),
    ("concentration_mg", "0.005", CONCENTRATION_MSG),
    ("concentration_mg", "-1", CONCENTRATION_MSG),
    ("stock", -1, STOCK_MSG),
    ("min_stock_alert", -1, MIN_STOCK_MSG),
]


class CatalogValueRulesTests(TestCase):
    def setUp(self) -> None:
        self.pharmacist = User.objects.create_user(
            email="farma_reglas@pokikoa.cl",
            full_name="Farmacia Reglas",
            password="Str0ng!Password2026",
            role=UserRole.PHARMACIST,
        )
        self.item = create_catalog_item(
            actor=self.pharmacist, name="Base", active_ingredient="Base", concentration_mg=10
        )

    def _create(self, **overrides) -> None:
        values = {"name": "Nuevo", "active_ingredient": "Activo", "concentration_mg": 1}
        values.update(overrides)
        create_catalog_item(actor=self.pharmacist, **values)

    def test_create_and_update_reject_the_same_values_with_the_same_message(self) -> None:
        for field, value, message in INVALID_VALUES:
            with self.subTest(flow="create", field=field, value=value):
                with self.assertRaises(DomainError) as ctx:
                    self._create(**{field: value})
                self.assertEqual(ctx.exception.message, message)
            with self.subTest(flow="update", field=field, value=value):
                with self.assertRaises(DomainError) as ctx:
                    update_catalog_item(actor=self.pharmacist, item=self.item, data={field: value})
                self.assertEqual(ctx.exception.message, message)

    def test_boundary_values_are_accepted_and_rounded(self) -> None:
        self._create(name="Limite", concentration_mg="0.006", stock=0, min_stock_alert=0)
        updated = update_catalog_item(
            actor=self.pharmacist,
            item=self.item,
            data={"concentration_mg": "0.006", "stock": 0, "min_stock_alert": 0},
        )
        self.assertEqual(updated.concentration_mg, Decimal("0.01"))
        self.assertEqual(updated.stock, 0)
