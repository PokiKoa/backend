from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from .models import UserRole


def _has_active_role(request: Request, allowed_roles: set[str]) -> bool:
    user = getattr(request, "user", None)
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", False)
        and getattr(user, "role", None) in allowed_roles
    )


class IsAdminRole(BasePermission):
    message = "Esta acción requiere rol de Administrador."

    def has_permission(self, request: Request, view: Any) -> bool:
        return _has_active_role(request, {UserRole.ADMIN})


class IsNeonatologistRole(BasePermission):
    message = "Esta acción requiere rol de Neonatólogo."

    def has_permission(self, request: Request, view: Any) -> bool:
        return _has_active_role(request, {UserRole.NEONATOLOGIST})


class IsNurseRole(BasePermission):
    message = "Esta acción requiere rol de Matrona o Enfermera."

    def has_permission(self, request: Request, view: Any) -> bool:
        return _has_active_role(request, {UserRole.NURSE})


class IsPharmacistRole(BasePermission):
    message = "Esta acción requiere rol de Químico Farmacéutico."

    def has_permission(self, request: Request, view: Any) -> bool:
        return _has_active_role(request, {UserRole.PHARMACIST})


class IsClinicalStaff(BasePermission):
    message = "Esta acción está restringida al personal clínico (Neonatólogo o Matrona/Enfermera)."

    def has_permission(self, request: Request, view: Any) -> bool:
        return _has_active_role(request, {UserRole.NEONATOLOGIST, UserRole.NURSE})
