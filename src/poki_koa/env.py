from pathlib import Path

import environ

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def load_env_file() -> None:
    # Debe ejecutarse antes de elegir DJANGO_SETTINGS_MODULE para que el .env pueda fijarlo;
    # las variables ya definidas en el entorno real tienen prioridad sobre el archivo.
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        environ.Env.read_env(str(env_file))
