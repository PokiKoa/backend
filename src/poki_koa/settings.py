"""Configuración del proyecto Django para Poki Koa.

Este archivo centraliza todos los ajustes del proyecto:
- Base de datos (SQLite para desarrollo)
- Apps instaladas (Django + DRF + CORS + cunas)
- CORS para permitir conexiones desde el frontend en Vite/React
- Internacionalización en español (zona horaria: América/Santiago)

Para producción, este archivo debe reemplazarse o extenderse con
variables de entorno y configuraciones seguras (DEBUG=False, etc.).
"""

import sys
from pathlib import Path

# Directorio raíz del proyecto: apunta a src/ (donde viven manage.py y las apps)
BASE_DIR = Path(__file__).resolve().parent.parent

# Agrega src/ al PYTHONPATH para que Django pueda importar las apps (cunas, poki_koa)
sys.path.append(str(BASE_DIR))

# CLAVE SECRETA — Solo válida para desarrollo local.
# En producción debe definirse como variable de entorno y nunca subirse al repositorio.
SECRET_KEY = "django-insecure-poki-koa-clave-de-desarrollo-local"

# Modo depuración: muestra errores detallados. Debe ser False en producción.
DEBUG = True

# Hosts permitidos. En desarrollo aceptamos cualquier host.
ALLOWED_HOSTS = ["*"]

# APLICACIONES INSTALADAS
INSTALLED_APPS = [
    # Apps nativas de Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Librerías de terceros
    "rest_framework",  # API REST (Django REST Framework)
    "corsheaders",  # Permite conexiones cross-origin desde el frontend
    # Apps del proyecto
    "cunas",  # App principal: modelos, vistas y API del sistema de cunas
]

# MIDDLEWARES — Se procesan en orden para cada request/response
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",  # Debe ir antes de CommonMiddleware para CORS
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# CORS — Orígenes autorizados para hacer peticiones al backend.
# El puerto 5173 es el servidor de desarrollo de Vite (frontend React).
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

ROOT_URLCONF = "poki_koa.urls"

# PLANTILLAS — Requerido por la app 'admin' de Django para renderizar su interfaz
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "poki_koa.wsgi.application"

# BASE DE DATOS
# SQLite es suficiente para desarrollo. En producción se recomienda PostgreSQL.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# VALIDADORES DE CONTRASEÑA — Reglas mínimas de seguridad para usuarios del sistema
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# INTERNACIONALIZACIÓN — Idioma y zona horaria del proyecto
LANGUAGE_CODE = "es-es"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True

# ARCHIVOS ESTÁTICOS (CSS, JavaScript, imágenes del panel admin)
STATIC_URL = "static/"

# Tipo de campo de clave primaria por defecto para todos los modelos nuevos
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CONFIGURACIÓN DE LOGGING — Permite visualizar trazas y eventos de negocio (INFO/WARNING)
# en consola durante la ejecución y depuración del proyecto (sin exponer datos sensibles).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "estandar": {
            "format": "[%(levelname)s] %(asctime)s %(name)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "consola": {
            "class": "logging.StreamHandler",
            "formatter": "estandar",
        },
    },
    "loggers": {
        "cunas": {
            "handlers": ["consola"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
