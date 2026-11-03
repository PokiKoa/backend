import sys
from datetime import timedelta
from pathlib import Path

import environ

from poki_koa.env import load_env_file

# Raíz de src/ para que las apps de dominio sean importables directamente
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

PROJECT_ROOT = BASE_DIR.parent

env = environ.Env()
load_env_file()

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "drf_spectacular",
    "accounts.apps.AccountsConfig",
    "audit.apps.AuditConfig",
    "devices.apps.DevicesConfig",
    "patients.apps.PatientsConfig",
    "vitals.apps.VitalsConfig",
    "alerts.apps.AlertsConfig",
    "medications.apps.MedicationsConfig",
    "reports.apps.ReportsConfig",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "poki_koa.urls"
WSGI_APPLICATION = "poki_koa.wsgi.application"
ASGI_APPLICATION = "poki_koa.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "poki_koa" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
    {
        "NAME": "accounts.validators.ClinicalPasswordValidator",
    },
]

LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = PROJECT_ROOT / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "poki_koa.pagination.StandardResultsSetPagination",
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "EXCEPTION_HANDLER": "poki_koa.exceptions.custom_exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "login": env("LOGIN_THROTTLE_RATE", default="5/min"),
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=env.int("JWT_ACCESS_MINUTES", default=15)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        hours=env.int("JWT_REFRESH_HOURS", default=8)
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# El refresh token solo viaja en una cookie httpOnly acotada a las rutas de autenticación,
# de modo que el JavaScript del frontend nunca lo lee (mitiga robo por XSS)
REFRESH_COOKIE = {
    "NAME": env("REFRESH_COOKIE_NAME", default="poki_refresh"),
    "PATH": "/api/v1/auth/",
    "DOMAIN": env("REFRESH_COOKIE_DOMAIN", default=None),
    "SAMESITE": env("REFRESH_COOKIE_SAMESITE", default="Lax"),
    "SECURE": env.bool("REFRESH_COOKIE_SECURE", default=False),
}
CORS_ALLOW_CREDENTIALS = True

SPECTACULAR_SETTINGS = {
    "TITLE": "Poki Koa API",
    "DESCRIPTION": "API REST y tiempo real para monitoreo clínico neonatal.",
    "VERSION": "2.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAuthenticated"],
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "ENUM_NAME_OVERRIDES": {
        "DischargeOutcomeEnum": "patients.models.DischargeOutcome",
        "DischargeCauseEnum": "patients.models.DischargeCause",
        "CribStatusEnum": "devices.models.CribStatus",
        "AlertSeverityEnum": "alerts.models.AlertSeverity",
        "AlertStatusEnum": "alerts.models.AlertStatus",
        "WorkShiftEnum": "accounts.models.WorkShift",
        "CarePlanStatusEnum": "patients.models.CarePlanStatus",
        "CribMovementKindEnum": "patients.models.CribMovementKind",
    },
}

REDIS_URL = env("REDIS_URL", default="")
if REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            # redis-py 8 usa socket_timeout=5 por defecto, igual que el BZPOPMIN de
            # channels-redis (brpop_timeout=5): la lectura expiraba y botaba el WebSocket
            "CONFIG": {"hosts": [{"address": REDIS_URL, "socket_timeout": 30}]},
        }
    }
else:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }
