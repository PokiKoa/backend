"""Validadores de contraseña propios del proyecto."""

import re
from typing import Any

from django.core.exceptions import ValidationError


class ClinicalPasswordValidator:
    """Exige mayúscula, minúscula, dígito y carácter especial en las contraseñas."""

    def validate(self, password: str, user: Any = None) -> None:
        """Valida la complejidad de la contraseña.

        Args:
            password: Contraseña a validar.
            user: Usuario asociado (no se usa).

        Raises:
            ValidationError: Con un mensaje por cada requisito incumplido (código ``password_complexity``).
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
        """Texto de ayuda con los requisitos de la contraseña."""
        return (
            "La contraseña debe tener al menos 10 caracteres e incluir mayúsculas, "
            "minúsculas, números y caracteres especiales."
        )
