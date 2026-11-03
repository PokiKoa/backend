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
    status_code = status.HTTP_401_UNAUTHORIZED
    default_code = "authentication_failed"
    default_message = "Credenciales de autenticación inválidas."


class AccountLockedError(DomainError):
    status_code = status.HTTP_423_LOCKED
    default_code = "account_locked"
    default_message = (
        "La cuenta se encuentra bloqueada temporalmente por múltiples intentos fallidos."
    )


class PermissionDomainError(DomainError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "permission_denied"
    default_message = "No tiene permisos para realizar esta acción."


class NotFoundDomainError(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    default_code = "not_found"
    default_message = "El recurso solicitado no existe."


class ConflictDomainError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"
    default_message = "La operación entra en conflicto con el estado actual del recurso."


def custom_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
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
        details = exc.message_dict if hasattr(exc, "message_dict") else {"non_field_errors": exc.messages}
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

    code = "api_error"
    message = "Error en la solicitud."
    details: Any = {}

    if isinstance(exc, ValidationError):
        code = "validation_error"
        message = "Los datos enviados no son válidos."
        details = response.data
    elif isinstance(exc, NotAuthenticated):
        code = "not_authenticated"
        message = "Se requieren credenciales de autenticación."
    elif isinstance(exc, AuthenticationFailed):
        code = "authentication_failed"
        message = "Credenciales de autenticación inválidas o expiradas."
    elif isinstance(exc, PermissionDenied):
        code = "permission_denied"
        message = "No tiene permisos para realizar esta acción."
    elif isinstance(exc, NotFound):
        code = "not_found"
        message = "El recurso solicitado no existe."
    elif isinstance(exc, MethodNotAllowed):
        code = "method_not_allowed"
        message = "Método HTTP no permitido en este recurso."
    elif isinstance(exc, Throttled):
        code = "rate_limit_exceeded"
        message = "Demasiadas solicitudes. Intente nuevamente más tarde."
    elif isinstance(exc, APIException):
        code = str(getattr(exc, "default_code", "api_error"))
        if isinstance(response.data, dict) and "detail" in response.data:
            message = str(response.data["detail"])

    response.data = {
        "error": {
            "code": code,
            "message": message,
            "details": details if isinstance(details, (dict, list)) else {},
        }
    }
    return response
