"""Un recurso inexistente responde 404 con el código ``not_found`` de la envoltura estándar."""

from django.test import TestCase

from accounts.models import User


class NotFoundEnvelopeTests(TestCase):
    def setUp(self) -> None:
        user = User.objects.create_user(
            username="medico", password="Clinica#2026", role="neonatologist"
        )
        self.client.force_login(user)

    def test_get_inexistente_responde_not_found(self) -> None:
        response = self.client.get("/api/v1/patients/999999/")
        self.assertEqual(response.status_code, 404)
        error = response.json()["error"]
        self.assertEqual(error["code"], "not_found")
        self.assertEqual(error["message"], "El recurso solicitado no existe.")
