"""Fuente única de los conjuntos de roles y de la guarda de rol de los servicios.

Los servicios de dominio y los permisos DRF (``accounts.permissions``) consumen
estas constantes para que cambiar quién puede ejecutar una operación requiera
editar un solo lugar.
"""

from collections.abc import Iterable

from poki_koa.exceptions import PermissionDomainError

from .models import User, UserRole

ADMIN_ONLY: frozenset[str] = frozenset({UserRole.ADMIN})
NEONATOLOGIST_ONLY: frozenset[str] = frozenset({UserRole.NEONATOLOGIST})
NURSE_ONLY: frozenset[str] = frozenset({UserRole.NURSE})
PHARMACIST_ONLY: frozenset[str] = frozenset({UserRole.PHARMACIST})
CLINICAL_STAFF: frozenset[str] = frozenset({UserRole.NEONATOLOGIST, UserRole.NURSE})
CLINICAL_OR_ADMIN: frozenset[str] = CLINICAL_STAFF | ADMIN_ONLY
THRESHOLD_MANAGERS: frozenset[str] = frozenset({UserRole.ADMIN, UserRole.NEONATOLOGIST})
CATALOG_MANAGERS: frozenset[str] = frozenset({UserRole.ADMIN, UserRole.PHARMACIST})


def has_role(user: User | None, allowed: Iterable[str]) -> bool:
    """Indica si ``user`` tiene uno de los roles de ``allowed``.

    Args:
        user: Usuario a evaluar; ``None`` o sin atributo ``role`` nunca califica.
        allowed: Conjunto de roles permitidos (usar las constantes de este módulo).

    Returns:
        ``True`` si el rol del usuario pertenece a ``allowed``.
    """
    return getattr(user, "role", None) in allowed


def require_role(actor: User, allowed: Iterable[str], message: str) -> None:
    """Exige que ``actor`` tenga uno de los roles de ``allowed``.

    Args:
        actor: Usuario que ejecuta la operación.
        allowed: Conjunto de roles permitidos (usar las constantes de este módulo).
        message: Mensaje en español que se devuelve al cliente si se rechaza.

    Raises:
        PermissionDomainError: Si el rol del actor no está permitido (HTTP 403).
    """
    if not has_role(actor, allowed):
        raise PermissionDomainError(message)
