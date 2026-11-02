import secrets
import sys

from .base import *
from .base import BASE_DIR, env

# En desarrollo se genera una clave efímera en memoria si no existe SECRET_KEY en el entorno
SECRET_KEY = env("SECRET_KEY", default="") or secrets.token_urlsafe(50)

DEBUG = env.bool("DEBUG", default=True)

ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS",
    default=["localhost", "127.0.0.1", "testserver"],
)

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    )
}

CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
)

if "pytest" in sys.modules or "test" in sys.argv:
    PASSWORD_HASHERS = [
        "django.contrib.auth.hashers.MD5PasswordHasher",
    ]
