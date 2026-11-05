"""Permisos DRF basados en el rol del usuario (RBAC)."""

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
    """Permite el acceso solo a usuarios activos con rol Administrador."""

    message = "Esta acción requiere rol de Administrador."

    def has_permission(self, request: Request, view: Any) -> bool:
        """Devuelve ``True`` si el usuario autenticado y activo es Administrador."""
        return _has_active_role(request, {UserRole.ADMIN})


class IsNeonatologistRole(BasePermission):
    """Permite el acceso solo a usuarios activos con rol Neonatólogo."""

    message = "Esta acción requiere rol de Neonatólogo."

    def has_permission(self, request: Request, view: Any) -> bool:
        """Devuelve ``True`` si el usuario autenticado y activo es Neonatólogo."""
        return _has_active_role(request, {UserRole.NEONATOLOGIST})


class IsNurseRole(BasePermission):
    """Permite el acceso solo a usuarios activos con rol Matrona/Enfermera."""

    message = "Esta acción requiere rol de Matrona o Enfermera."

    def has_permission(self, request: Request, view: Any) -> bool:
        """Devuelve ``True`` si el usuario autenticado y activo es Matrona/Enfermera."""
        return _has_active_role(request, {UserRole.NURSE})


class IsPharmacistRole(BasePermission):
    """Permite el acceso solo a usuarios activos con rol Químico Farmacéutico."""

    message = "Esta acción requiere rol de Químico Farmacéutico."

    def has_permission(self, request: Request, view: Any) -> bool:
        """Devuelve ``True`` si el usuario autenticado y activo es Químico Farmacéutico."""
        return _has_active_role(request, {UserRole.PHARMACIST})


class IsClinicalStaff(BasePermission):
    """Permite el acceso al personal clínico: Neonatólogo o Matrona/Enfermera activos."""

    message = "Esta acción está restringida al personal clínico (Neonatólogo o Matrona/Enfermera)."

    def has_permission(self, request: Request, view: Any) -> bool:
        """Devuelve ``True`` si el usuario autenticado y activo es Neonatólogo o Matrona/Enfermera."""
        return _has_active_role(request, {UserRole.NEONATOLOGIST, UserRole.NURSE})
