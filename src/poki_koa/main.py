"""Punto de entrada de la CLI ``poki_koa`` (equivalente a ``manage.py``)."""

import os
import sys
from pathlib import Path


def main() -> None:
    """Ejecuta un comando de Django (``runserver`` por defecto) con ``settings.dev`` si no se indica otra configuración."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "poki_koa.settings.dev")

    src_dir = str(Path(__file__).resolve().parent.parent)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    from django.core.management import execute_from_command_line

    args = sys.argv.copy()
    if len(args) <= 1:
        args.append("runserver")
    elif len(args) == 2 and args[1] == "test" and Path("src").exists():
        os.chdir("src")

    execute_from_command_line(args)
