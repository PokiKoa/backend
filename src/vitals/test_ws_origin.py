from urllib.parse import urlparse

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import User, UserRole
from poki_koa.asgi import application

from .realtime import SettingsOriginValidator
from .tests import WebsocketCommunicator

STREAM = "/ws/v1/monitoring/stream/"


def _is_valid(origin: str | None) -> bool:
    validator = SettingsOriginValidator(application=None)
    return validator.valid_origin(urlparse(origin) if origin is not None else None)


class SettingsOriginValidatorTests(SimpleTestCase):
    @override_settings(ALLOWED_HOSTS=["pokikoa.racsu.com"], CORS_ALLOWED_ORIGINS=[])
    def test_same_origin_as_allowed_host_is_accepted(self) -> None:
        self.assertTrue(_is_valid("https://pokikoa.racsu.com"))

    @override_settings(ALLOWED_HOSTS=["pokikoa.racsu.com"], CORS_ALLOWED_ORIGINS=[])
    def test_foreign_or_missing_origin_is_rejected(self) -> None:
        self.assertFalse(_is_valid("https://evil.example"))
        self.assertFalse(_is_valid("https://pokikoa.racsu.com.evil.example"))
        self.assertFalse(_is_valid(None))

    @override_settings(
        ALLOWED_HOSTS=["api.pokikoa.example"],
        CORS_ALLOWED_ORIGINS=["https://app.pokikoa.example"],
    )
    def test_cors_allowed_origin_is_accepted_with_exact_scheme_and_port(self) -> None:
        self.assertTrue(_is_valid("https://app.pokikoa.example"))
        self.assertFalse(_is_valid("http://app.pokikoa.example"))
        self.assertFalse(_is_valid("https://app.pokikoa.example:8443"))

    @override_settings(DEBUG=True, ALLOWED_HOSTS=[], CORS_ALLOWED_ORIGINS=[])
    def test_debug_without_allowed_hosts_accepts_localhost(self) -> None:
        self.assertTrue(_is_valid("http://localhost:5173"))
        self.assertFalse(_is_valid("http://evil.example"))

    @override_settings(DEBUG=False, ALLOWED_HOSTS=[], CORS_ALLOWED_ORIGINS=[])
    def test_production_without_allowed_hosts_rejects_localhost(self) -> None:
        self.assertFalse(_is_valid("http://localhost:5173"))


class WebSocketOriginHandshakeTests(TransactionTestCase):
    def setUp(self) -> None:
        nurse = User.objects.create_user(
            email="origen_ws@pokikoa.cl",
            full_name="Matrona Origen",
            password="Str0ng!Password2026",
            role=UserRole.NURSE,
        )
        self.token = str(AccessToken.for_user(nurse))

    def _connect(self, origin: bytes | None) -> tuple[bool, int | str | None]:
        async def _run() -> tuple[bool, int | str | None]:
            comm = WebsocketCommunicator(
                application, STREAM, subprotocols=["bearer", self.token], origin=origin
            )
            result = await comm.connect()
            if result[0]:
                await comm.disconnect()
            return result

        return async_to_sync(_run)()

    @override_settings(ALLOWED_HOSTS=["pokikoa.racsu.com"], CORS_ALLOWED_ORIGINS=[])
    def test_valid_token_from_foreign_origin_is_rejected(self) -> None:
        connected, _ = self._connect(b"https://evil.example")
        self.assertFalse(connected)

    @override_settings(ALLOWED_HOSTS=["pokikoa.racsu.com"], CORS_ALLOWED_ORIGINS=[])
    def test_valid_token_without_origin_is_rejected(self) -> None:
        connected, _ = self._connect(None)
        self.assertFalse(connected)

    @override_settings(ALLOWED_HOSTS=["pokikoa.racsu.com"], CORS_ALLOWED_ORIGINS=[])
    def test_same_origin_frontend_connects(self) -> None:
        connected, subprotocol = self._connect(b"https://pokikoa.racsu.com")
        self.assertTrue(connected)
        self.assertEqual(subprotocol, "bearer")

    @override_settings(
        ALLOWED_HOSTS=["api.pokikoa.example"],
        CORS_ALLOWED_ORIGINS=["https://app.pokikoa.example"],
    )
    def test_frontend_listed_in_cors_allowed_origins_connects(self) -> None:
        connected, _ = self._connect(b"https://app.pokikoa.example")
        self.assertTrue(connected)
