"""Punto de entrada principal del proyecto Poki Koa.

Este módulo define la función `main()` que actúa como punto de entrada del
comando `poki_koa` registrado en pyproject.toml. Permite ejecutar cualquier
comando de gestión de Django directamente desde la raíz del proyecto usando:

    uv run poki_koa             → Inicia el servidor de desarrollo
    uv run poki_koa migrate     → Aplica las migraciones de base de datos
    uv run poki_koa test        → Ejecuta la suite de pruebas unitarias
"""

import os
import sys

from django.core.management import execute_from_command_line

"""Función principal que configura el entorno Django y delega la ejecución al sistema de gestión de comandos de Django.

Comportamiento especial:
- Sin argumentos: ejecuta 'runserver' por defecto.
- Con argumento 'test' (sin app específica): cambia al directorio src/
  para que el descubridor automático de tests encuentre los módulos.

@returns None
"""


def main() -> None:
    # Configura el módulo de ajustes de Django si no está ya definido
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "poki_koa.settings")

    args = sys.argv.copy()

    # Si no se pasa ningún comando, levantar el servidor de desarrollo
    if len(args) <= 1:
        args.append("runserver")

    # Si se ejecuta 'test' sin especificar una app, moverse a src/ para que
    # Django pueda descubrir automáticamente los archivos tests.py de cada app
    if len(args) == 2 and args[1] == "test" and os.path.exists("src"):
        os.chdir("src")

    execute_from_command_line(args)


if __name__ == "__main__":
    main()
