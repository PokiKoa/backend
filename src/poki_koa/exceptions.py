"""Excepciones de dominio y manejador global que unifica el formato de error de la API."""

from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    MethodNotAllowed,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    Throttled,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler


class DomainError(Exception):
    """Error de negocio con código HTTP, código de error y detalles por campo.

    Los servicios lanzan subclases; ``custom_exception_handler`` las traduce a
    ``{"error": {"code", "message", "details"}}``. Por defecto responde 400.
    """

    status_code: int = status.HTTP_400_BAD_REQUEST
    default_code: str = "domain_error"
    default_message: str = "Error en la operación solicitada."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.code = code or self.default_code
        self.details = details or {}
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.message)


class AuthenticationDomainError(DomainError):
    """Credenciales o token inválidos (HTTP 401)."""

    status_code = status.HTTP_401_UNAUTHORIZED
    default_code = "authentication_failed"
    default_message = "Credenciales de autenticación inválidas."


class AccountLockedError(DomainError):
    """Cuenta bloqueada temporalmente por intentos fallidos (HTTP 423)."""

    status_code = status.HTTP_423_LOCKED
    default_code = "account_locked"
    default_message = (
        "La cuenta se encuentra bloqueada temporalmente por múltiples intentos fallidos."
    )


class PermissionDomainError(DomainError):
    """El rol del usuario no permite la operación (HTTP 403)."""

    status_code = status.HTTP_403_FORBIDDEN
    default_code = "permission_denied"
    default_message = "No tiene permisos para realizar esta acción."


class NotFoundDomainError(DomainError):
    """El recurso referenciado no existe (HTTP 404)."""

    status_code = status.HTTP_404_NOT_FOUND
    default_code = "not_found"
    default_message = "El recurso solicitado no existe."


class ConflictDomainError(DomainError):
    """La operación choca con el estado actual del recurso (HTTP 409)."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"
    default_message = "La operación entra en conflicto con el estado actual del recurso."


# (excepción DRF, código, mensaje) evaluados en orden: la primera coincidencia gana.
_API_EXCEPTION_DESCRIPTIONS: tuple[tuple[type[Exception], str, str], ...] = (
    (ValidationError, "validation_error", "Los datos enviados no son válidos."),
    (NotAuthenticated, "not_authenticated", "Se requieren credenciales de autenticación."),
    (
        AuthenticationFailed,
        "authentication_failed",
        "Credenciales de autenticación inválidas o expiradas.",
    ),
    (PermissionDenied, "permission_denied", "No tiene permisos para realizar esta acción."),
    (NotFound, "not_found", "El recurso solicitado no existe."),
    (MethodNotAllowed, "method_not_allowed", "Método HTTP no permitido en este recurso."),
    (
        Throttled,
        "rate_limit_exceeded",
        "Demasiadas solicitudes. Intente nuevamente más tarde.",
    ),
)


def _describe_api_exception(exc: Exception, response_data: Any) -> tuple[str, str]:
    """Devuelve el ``(code, message)`` de la envoltura de error para una excepción DRF."""
    for exc_type, code, message in _API_EXCEPTION_DESCRIPTIONS:
        if isinstance(exc, exc_type):
            return code, message
    if isinstance(exc, APIException):
        code = str(getattr(exc, "default_code", "api_error"))
        if isinstance(response_data, dict) and "detail" in response_data:
            return code, str(response_data["detail"])
        return code, "Error en la solicitud."
    return "api_error", "Error en la solicitud."


def custom_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Traduce cualquier excepción a la envoltura de error estándar de la API.

    Args:
        exc: Excepción levantada por la vista.
        context: Contexto de DRF (vista, petición).

    Returns:
        Respuesta con ``{"error": {"code", "message", "details"}}``, o ``None`` si la excepción no
        es de API y debe propagarse (error 500).
    """
    if isinstance(exc, DomainError):
        return Response(
            {
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
            status=exc.status_code,
        )

    if isinstance(exc, DjangoValidationError):
        details = (
            exc.message_dict if hasattr(exc, "message_dict") else {"non_field_errors": exc.messages}
        )
        return Response(
            {
                "error": {
                    "code": "validation_error",
                    "message": "Los datos enviados no son válidos.",
                    "details": details,
                }
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if isinstance(exc, ObjectDoesNotExist):
        return Response(
            {
                "error": {
                    "code": "not_found",
                    "message": "El recurso solicitado no existe.",
                    "details": {},
                }
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    response = exception_handler(exc, context)
    if response is None:
        return None

    code, message = _describe_api_exception(exc, response.data)
    details: Any = response.data if isinstance(exc, ValidationError) else {}

    response.data = {
        "error": {
            "code": code,
            "message": message,
            "details": details if isinstance(details, (dict, list)) else {},
        }
    }
    return response
