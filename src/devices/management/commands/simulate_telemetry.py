import json
import random
import time
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.models import User, UserRole
from devices.models import Crib, CribStatus
from devices.services import rotate_crib_api_key
from poki_koa.exceptions import DomainError
from vitals.services import ingest_telemetry
from vitals.simulation import SimulatedCribState, next_payload


class Command(BaseCommand):
    help = (
        "Simula telemetría de cunas ocupadas para desarrollo del frontend "
        "(solo con DEBUG=True). Genera episodios fuera de rango y su recuperación."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--mode",
            choices=["http", "direct"],
            default="http",
            help=(
                "http (por defecto): envía lecturas al servidor en ejecución con la API Key de cada cuna, "
                "para que los WebSockets las reciban sin Redis. direct: ingiere en este proceso "
                "(requiere REDIS_URL para que el servidor emita los eventos)."
            ),
        )
        parser.add_argument("--base-url", default="http://127.0.0.1:8000")
        parser.add_argument("--interval", type=float, default=5.0, help="Segundos entre rondas.")
        parser.add_argument(
            "--iterations", type=int, default=0, help="Número de rondas (0 = sin límite)."
        )
        parser.add_argument(
            "--cribs",
            default="",
            help="Códigos de cuna separados por coma (por defecto: todas las ocupadas).",
        )
        parser.add_argument(
            "--anomaly-rate",
            type=float,
            default=0.05,
            help="Probabilidad por lectura de iniciar un episodio anómalo (0 a 1).",
        )
        parser.add_argument("--seed", type=int, default=None)

    def handle(self, *args, **options) -> None:
        # Rotar API keys invalida las credenciales de dispositivos reales: nunca en producción
        if not settings.DEBUG:
            raise CommandError("El simulador de telemetría solo puede ejecutarse con DEBUG=True.")
        if not 0 <= options["anomaly_rate"] <= 1:
            raise CommandError("--anomaly-rate debe estar entre 0 y 1.")

        cribs = self._select_cribs(options["cribs"])
        if not cribs:
            raise CommandError(
                "No hay cunas ocupadas y activas para simular. Ejecuta seed_demo o indica --cribs."
            )

        mode: str = options["mode"]
        api_keys = self._issue_api_keys(cribs) if mode == "http" else {}
        if mode == "direct" and not getattr(settings, "REDIS_URL", ""):
            self.stdout.write(
                self.style.WARNING(
                    "Sin REDIS_URL los eventos WebSocket no llegarán al servidor; usa --mode http."
                )
            )

        rng = random.Random(options["seed"])
        states = {crib.id: SimulatedCribState() for crib in cribs}
        self.stdout.write(
            f"Simulando {len(cribs)} cuna(s): {', '.join(c.code for c in cribs)} (modo {mode})."
        )

        iteration = 0
        try:
            while options["iterations"] == 0 or iteration < options["iterations"]:
                if iteration:
                    time.sleep(options["interval"])
                iteration += 1
                for crib in cribs:
                    payload = next_payload(
                        states[crib.id], rng, anomaly_rate=options["anomaly_rate"]
                    )
                    if mode == "http":
                        self._send_http(options["base_url"], crib, api_keys[crib.id], payload)
                    else:
                        self._send_direct(crib, payload)
        except KeyboardInterrupt:
            self.stdout.write("Simulación detenida.")

    def _select_cribs(self, raw_codes: str) -> list[Crib]:
        qs = Crib.objects.filter(is_device_active=True).exclude(status=CribStatus.MAINTENANCE)
        codes = [c.strip().upper() for c in raw_codes.split(",") if c.strip()]
        if codes:
            qs = qs.filter(code__in=codes)
        else:
            qs = qs.filter(current_patient__isnull=False)
        return list(qs.order_by("code"))

    def _issue_api_keys(self, cribs: list[Crib]) -> dict[int, str]:
        admin = User.objects.filter(role=UserRole.ADMIN, is_active=True).order_by("id").first()
        if admin is None:
            raise CommandError("Se necesita un usuario administrador activo para emitir API keys.")
        return {crib.id: rotate_crib_api_key(actor=admin, crib=crib) for crib in cribs}

    def _send_http(self, base_url: str, crib: Crib, api_key: str, payload: dict[str, Any]) -> None:
        request = urllib.request.Request(
            f"{base_url.rstrip('/')}/api/v1/cribs/{crib.id}/telemetry/",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "X-Device-Api-Key": api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                body = json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as exc:
            self.stderr.write(f"{crib.code}: HTTP {exc.code} {exc.read()[:200]!r}")
            return
        except urllib.error.URLError as exc:
            raise CommandError(
                f"No se pudo conectar con {base_url}: {exc.reason}. ¿Está el servidor en ejecución?"
            ) from exc
        self._report(crib, len(body.get("active_alerts", [])))

    def _send_direct(self, crib: Crib, payload: dict[str, Any]) -> None:
        try:
            _, evaluation = ingest_telemetry(
                crib=crib, payload=payload, is_device_authenticated=True
            )
        except DomainError as exc:
            self.stderr.write(f"{crib.code}: {exc}")
            return
        self._report(crib, len(evaluation.active_or_updated_alerts))

    def _report(self, crib: Crib, alert_count: int) -> None:
        # Solo se informa el conteo de alertas: los valores clínicos no se vuelcan en la salida
        if alert_count:
            self.stdout.write(
                self.style.WARNING(
                    f"{crib.code}: lectura enviada, {alert_count} alerta(s) activa(s)"
                )
            )
        else:
            self.stdout.write(f"{crib.code}: lectura enviada")
