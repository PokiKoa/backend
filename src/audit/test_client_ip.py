from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User, UserRole
from audit.models import AuditAction, AuditLog
from audit.services import get_client_ip

LOGIN_URL = "/api/v1/auth/login/"


class ClientIpTests(SimpleTestCase):
    def _request(self, remote_addr: str = "10.0.0.2", forwarded_for: str | None = None):
        extra = {"REMOTE_ADDR": remote_addr}
        if forwarded_for is not None:
            extra["HTTP_X_FORWARDED_FOR"] = forwarded_for
        return RequestFactory().get("/", **extra)

    def test_without_request_returns_none(self) -> None:
        self.assertIsNone(get_client_ip(None))
        self.assertIsNone(get_client_ip(object()))

    @override_settings(TRUSTED_PROXY_COUNT=0)
    def test_without_trusted_proxies_ignores_spoofed_header(self) -> None:
        request = self._request(forwarded_for="203.0.113.66")
        self.assertEqual(get_client_ip(request), "10.0.0.2")

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_one_proxy_uses_last_hop_and_ignores_client_prefix(self) -> None:
        # El cliente envía "203.0.113.66" falsa; el proxy agrega la IP real a la derecha
        request = self._request(forwarded_for="203.0.113.66, 198.51.100.7")
        self.assertEqual(get_client_ip(request), "198.51.100.7")

    @override_settings(TRUSTED_PROXY_COUNT=2)
    def test_two_proxies_skip_the_inner_proxy_hop(self) -> None:
        request = self._request(forwarded_for="203.0.113.66, 198.51.100.7, 172.18.0.5")
        self.assertEqual(get_client_ip(request), "198.51.100.7")

    @override_settings(TRUSTED_PROXY_COUNT=2)
    def test_fewer_hops_than_trusted_proxies_falls_back_to_remote_addr(self) -> None:
        request = self._request(forwarded_for="203.0.113.66")
        self.assertEqual(get_client_ip(request), "10.0.0.2")

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_missing_or_invalid_header_falls_back_to_remote_addr(self) -> None:
        self.assertEqual(get_client_ip(self._request()), "10.0.0.2")
        self.assertEqual(get_client_ip(self._request(forwarded_for="no-es-ip")), "10.0.0.2")
        self.assertEqual(get_client_ip(self._request(forwarded_for=" , ")), "10.0.0.2")

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_ipv6_hop_is_normalized(self) -> None:
        request = self._request(forwarded_for="2001:DB8::1")
        self.assertEqual(get_client_ip(request), "2001:db8::1")

    @override_settings(TRUSTED_PROXY_COUNT=0)
    def test_invalid_remote_addr_returns_none(self) -> None:
        self.assertIsNone(get_client_ip(self._request(remote_addr="")))


class ForwardedForSpoofingTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.client = APIClient()
        self.password = "PasswordSegura!2026"
        self.nurse = User.objects.create_user(
            email="ip.matrona@pokikoa.cl",
            full_name="Matrona IP",
            password=self.password,
            role=UserRole.NURSE,
        )

    def _login(self, forwarded_for: str, password: str | None = None):
        return self.client.post(
            LOGIN_URL,
            {"email": self.nurse.email, "password": password or self.password},
            format="json",
            REMOTE_ADDR="10.0.0.2",
            HTTP_X_FORWARDED_FOR=forwarded_for,
        )

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_audit_log_stores_proxy_reported_ip_not_client_supplied(self) -> None:
        res = self._login("203.0.113.66, 198.51.100.7")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        log = AuditLog.objects.get(action=AuditAction.LOGIN_SUCCESS, actor_user=self.nurse)
        self.assertEqual(log.ip_address, "198.51.100.7")

    def test_audit_log_ignores_header_without_trusted_proxies(self) -> None:
        self._login("203.0.113.66")
        log = AuditLog.objects.get(action=AuditAction.LOGIN_SUCCESS, actor_user=self.nurse)
        self.assertEqual(log.ip_address, "10.0.0.2")

    @override_settings(
        REST_FRAMEWORK={
            "EXCEPTION_HANDLER": "poki_koa.exceptions.custom_exception_handler",
            "DEFAULT_THROTTLE_RATES": {"login": "3/min"},
            "NUM_PROXIES": 0,
        }
    )
    def test_rotating_forwarded_for_does_not_bypass_login_throttle(self) -> None:
        for attempt in range(3):
            res = self._login(f"203.0.113.{attempt}", password="incorrecta")
            self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        throttled = self._login("203.0.113.99", password="incorrecta")
        self.assertEqual(throttled.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
