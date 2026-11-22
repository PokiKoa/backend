"""Validadores de contraseña propios del proyecto."""

import re
from typing import Any

from django.core.exceptions import ValidationError


class ClinicalPasswordValidator:
    """Validador de complejidad robusto para las contraseñas del sistema clínico."""

    def validate(self, password: str, user: Any = None) -> None:
        """Valida que la contraseña cumpla con los requisitos mínimos de complejidad
        (incluyendo mayúsculas, minúsculas, dígitos y caracteres especiales).

        Args:
            password: Cadena de texto de la contraseña a validar.
            user: Instancia de usuario opcional asociada a la validación (no utilizada).

        Raises:
            ValidationError: Si se detecta el incumplimiento de uno o más requisitos,
            agrupando los mensajes bajo el código ``password_complexity``.
        """
        errors: list[str] = []
        if not re.search(r"[A-Z]", password):
            errors.append("La contraseña debe incluir al menos una letra mayúscula.")
        if not re.search(r"[a-z]", password):
            errors.append("La contraseña debe incluir al menos una letra minúscula.")
        if not re.search(r"\d", password):
            errors.append("La contraseña debe incluir al menos un dígito numérico.")
        if not re.search(r"[^A-Za-z0-9]", password):
            errors.append("La contraseña debe incluir al menos un carácter especial.")
        if errors:
            raise ValidationError(errors, code="password_complexity")

    def get_help_text(self) -> str:
        """Proporciona un texto descriptivo de ayuda sobre los requisitos de complejidad
        que debe cumplir la contraseña.

        Returns:
            str: Descripción orientativa para las interfaces de usuario o formularios.
        """
        return (
            "La contraseña debe tener al menos 10 caracteres e incluir mayúsculas, "
            "minúsculas, números y caracteres especiales."
        )
