from django.core.management.base import BaseCommand

from devices.services import detect_offline_cribs


class Command(BaseCommand):
    help = "Detecta cunas sin telemetría reciente, actualiza su estado a offline y genera alertas de fallo de señal."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--timeout-seconds",
            type=int,
            default=120,
            help="Segundos máximos permitidos desde la última lectura antes de marcar una cuna como offline (por defecto: 120).",
        )

    def handle(self, *args, **options) -> None:
        timeout_seconds: int = options["timeout_seconds"]
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
