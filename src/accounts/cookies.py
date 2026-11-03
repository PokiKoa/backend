from django.conf import settings
from rest_framework.request import Request
from rest_framework.response import Response

from poki_koa.exceptions import PermissionDomainError


def _config() -> dict:
    return settings.REFRESH_COOKIE


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    config = _config()
    response.set_cookie(
        config["NAME"],
        refresh_token,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        path=config["PATH"],
        domain=config["DOMAIN"],
        secure=config["SECURE"],
        httponly=True,
        samesite=config["SAMESITE"],
    )


def clear_refresh_cookie(response: Response) -> None:
    config = _config()
    response.delete_cookie(
        config["NAME"], path=config["PATH"], domain=config["DOMAIN"], samesite=config["SAMESITE"]
    )


def read_refresh_cookie(request: Request) -> str:
    # El navegador adjunta la cookie de forma automática: se exige un Origin conocido para que
    # otro sitio no pueda rotar ni revocar la sesión (CSRF) cuando SameSite=None
    origin = request.headers.get("Origin")
    if origin:
        own_origin = f"{request.scheme}://{request.get_host()}"
        allowed = set(getattr(settings, "CORS_ALLOWED_ORIGINS", [])) | {own_origin}
        if origin.rstrip("/") not in allowed:
            raise PermissionDomainError("Origen no autorizado para usar la sesión.")
    return request.COOKIES.get(_config()["NAME"], "")
