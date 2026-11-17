"""Normalización y validación de datos de contacto de los padres (RUT y teléfono chilenos)."""

import re

from poki_koa.exceptions import DomainError

_RUT_PATTERN = re.compile(r"^(\d{1,8})([\dK])$")


def rut_check_digit(body: str) -> str:
    """Calcula el dígito verificador de un RUT chileno mediante módulo 11.

    Args:
        body: Parte numérica del RUT sin puntos ni guion (1 a 8 dígitos).

    Returns:
        Dígito verificador normalizado en mayúscula (``"0"``–``"9"`` o ``"K"``).
    """
    total = 0
    factor = 2
    for digit in reversed(body):
        total += int(digit) * factor
        factor = 2 if factor == 7 else factor + 1
    remainder = 11 - (total % 11)
    if remainder == 11:
        return "0"
    if remainder == 10:
        return "K"
    return str(remainder)


def normalize_rut(value: str, *, label: str) -> str:
    """Normaliza y valida un RUT chileno en formato ``12345678-5``.

    Args:
        value: Cadena de entrada con o sin puntos, guion o espacios.
        label: Etiqueta contextual del apoderado para mensajes de error (ej. ``"de la madre"``).

    Returns:
        RUT normalizado como ``12345678-5``, o cadena vacía si ``value`` viene en blanco.

    Raises:
        DomainError: Si el formato es inválido o el dígito verificador no coincide.
    """
    raw = (value or "").strip().upper().replace(".", "").replace("-", "").replace(" ", "")
    if not raw:
        return ""
    match = _RUT_PATTERN.match(raw)
    if match is None:
        raise DomainError(f"El RUT {label} no tiene un formato válido (ej. 12.345.678-5).")
    body, check_digit = match.groups()
    body = body.lstrip("0") or "0"
    if rut_check_digit(body) != check_digit:
        raise DomainError(f"El RUT {label} no es válido: el dígito verificador no coincide.")
    return f"{body}-{check_digit}"


def normalize_phone(value: str, *, label: str) -> str:
    """Normaliza y valida un teléfono chileno al formato internacional ``+56XXXXXXXXX``.

    Args:
        value: Número telefónico de entrada con o sin prefijo ``+56`` / ``56`` y separadores.
        label: Etiqueta contextual del apoderado para mensajes de error (ej. ``"del padre"``).

    Returns:
        Teléfono normalizado en 12 caracteres (``+56`` + 9 dígitos), o cadena vacía si no se informó.

    Raises:
        DomainError: Si tiene prefijo extranjero o no contiene exactamente 9 dígitos nacionales.
    """
    raw = (value or "").strip()
    if not raw:
        return ""
    digits = re.sub(r"[\s\-().]", "", raw)
    if digits.startswith("+"):
        digits = digits[1:]
        if not digits.startswith("56"):
            raise DomainError(f"El teléfono {label} debe ser un número chileno (+56).")
    if digits.startswith("56") and len(digits) == 11:
        digits = digits[2:]
    if not digits.isdigit() or len(digits) != 9:
        raise DomainError(f"El teléfono {label} debe tener 9 dígitos (ej. +56 9 1234 5678).")
    return f"+56{digits}"
