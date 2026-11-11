"""Integración con drf-spectacular: genera el esquema en memoria y comprueba el
contrato que consume el frontend (``openapi-typescript``).

Detecta un cambio incompatible al actualizar drf-spectacular (Guía Unidad 3, §6).
"""

from django.test import SimpleTestCase
from drf_spectacular.generators import SchemaGenerator

FRONTEND_PATHS = [
    "/api/v1/auth/login/",
    "/api/v1/audit-logs/",
    "/api/v1/reports/summary/",
    "/api/v1/reports/series/",
]


class OpenApiContractTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.schema = SchemaGenerator().get_schema(request=None, public=True)

    def test_schema_is_openapi_3(self) -> None:
        self.assertTrue(self.schema["openapi"].startswith("3."))

    def test_frontend_paths_are_present(self) -> None:
        for path in FRONTEND_PATHS:
            with self.subTest(path=path):
                self.assertIn(path, self.schema["paths"])

    def test_audit_log_component_keeps_the_fields_used_by_the_frontend(self) -> None:
        properties = self.schema["components"]["schemas"]["AuditLog"]["properties"]
        for field in ("action", "resource_type", "changed_fields", "timestamp", "ip_address"):
            with self.subTest(field=field):
                self.assertIn(field, properties)
