"""Comando que detecta cunas sin telemetría reciente."""

import time

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from devices.services import detect_offline_cribs


class Command(BaseCommand):
    """Marca como offline las cunas sin lecturas recientes y genera sus alertas de pérdida de señal."""

    help = "Detecta cunas sin telemetría reciente, actualiza su estado a offline y genera alertas de fallo de señal."

    def add_arguments(self, parser) -> None:
        """Declara ``--timeout-seconds``, ``--every`` y ``--max-runs``."""
        parser.add_argument(
            "--timeout-seconds",
            type=int,
            default=120,
            help="Segundos máximos permitidos desde la última lectura antes de marcar una cuna como offline (por defecto: 120).",
        )
        parser.add_argument(
            "--every",
            type=int,
            default=0,
            help="Repite la verificación cada N segundos sin terminar (0 = una sola vez).",
        )
        parser.add_argument(
            "--max-runs",
            type=int,
            default=0,
            help="Límite de ejecuciones con --every (0 = sin límite).",
        )

    def handle(self, *args, **options) -> None:
        """Ejecuta la verificación una vez o la repite cada ``--every`` segundos.

        Raises:
            CommandError: Si ``--every`` es negativo.
        """
        timeout_seconds: int = options["timeout_seconds"]
        every: int = options["every"]
        if every < 0:
            raise CommandError("--every no puede ser negativo.")
        if not every:
            self._run_once(timeout_seconds)
            return

        runs = 0
        try:
            while not options["max_runs"] or runs < options["max_runs"]:
                if runs:
                    time.sleep(every)
                runs += 1
                try:
                    self._run_once(timeout_seconds)
                except DatabaseError as exc:
                    # Un fallo transitorio (p. ej. migraciones aún no aplicadas) no debe detener el monitor
                    self.stderr.write(f"Error de base de datos al verificar cunas: {exc}")
        except KeyboardInterrupt:
            self.stdout.write("Monitor de cunas detenido.")

    def _run_once(self, timeout_seconds: int) -> None:
        offline_cribs = detect_offline_cribs(timeout_seconds=timeout_seconds)
        if offline_cribs:
            codes = ", ".join(c.code for c in offline_cribs)
            self.stdout.write(
                self.style.WARNING(
                    f"Se marcaron {len(offline_cribs)} cuna(s) como offline ({codes})."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Sin cunas desconectadas (umbral evaluado: {timeout_seconds} s)."
                )
            )
