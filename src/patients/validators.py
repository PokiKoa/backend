"""Normalización y validación de datos de contacto de los padres (RUT y teléfono chilenos)."""

import re

from poki_koa.exceptions import DomainError

_RUT_PATTERN = re.compile(r"^(\d{1,8})([\dK])$")


def rut_check_digit(body: str) -> str:
    """Calcula el dígito verificador de un RUT con el algoritmo módulo 11."""
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
    """Devuelve el RUT como ``12345678-5`` o cadena vacía si no se informó.

    Acepta puntos, guion y ``k`` minúscula; rechaza formatos inválidos o un
    dígito verificador que no corresponda.
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
    """Devuelve el teléfono chileno como ``+56XXXXXXXXX`` o cadena vacía si no se informó.

    Acepta espacios, guiones, paréntesis y el prefijo ``+56`` o ``56``; el número
    nacional debe tener 9 dígitos (celular ``9XXXXXXXX`` o fijo con código de área).
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
        raise DomainError(
            f"El teléfono {label} debe tener 9 dígitos (ej. +56 9 1234 5678)."
        )
    return f"+56{digits}"
