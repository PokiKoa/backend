from datetime import time
from typing import Any, ClassVar

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


class UserRole(models.TextChoices):
    ADMIN = "admin", "Administrador"
    NEONATOLOGIST = "neonatologist", "Neonatólogo"
    NURSE = "nurse", "Matrona / Enfermera"
    PHARMACIST = "pharmacist", "Químico Farmacéutico"


class WorkShift(models.TextChoices):
    MORNING = "morning", "Mañana"
    AFTERNOON = "afternoon", "Tarde"
    NIGHT = "night", "Noche"


# Fuente única de verdad del horario de cada turno (hora local); la noche cruza la medianoche
# y pertenece a la fecha en que comienza
SHIFT_HOURS: dict[str, tuple[time, time]] = {
    WorkShift.MORNING: (time(7, 0), time(15, 0)),
    WorkShift.AFTERNOON: (time(15, 0), time(23, 0)),
    WorkShift.NIGHT: (time(23, 0), time(7, 0)),
}


class UserManager(BaseUserManager["User"]):
    def create_user(
        self,
        username: str | None = None,
        full_name: str | None = None,
        password: str | None = None,
        email: str = "",
        **extra_fields: Any,
    ) -> "User":
        effective_username = (username or "").strip().lower()
        normalized_email = (
            self.normalize_email(email.strip()).lower() if email and email.strip() else ""
        )
        if not effective_username and normalized_email:
            effective_username = normalized_email.split("@")[0]

        if not effective_username:
            raise ValueError("El nombre de usuario es obligatorio.")

        effective_full_name = (full_name or effective_username).strip()
        if not effective_full_name:
            raise ValueError("El nombre completo es obligatorio.")

        user = self.model(
            username=effective_username,
            email=normalized_email,
            full_name=effective_full_name,
            **extra_fields,
        )
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(
        self,
        username: str,
        full_name: str = "Administrador",
        password: str | None = None,
        email: str = "",
        **extra_fields: Any,
    ) -> "User":
        extra_fields.setdefault("role", UserRole.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        return self.create_user(
            username=username,
            full_name=full_name,
            password=password,
            email=email,
            **extra_fields,
        )


class User(AbstractBaseUser, PermissionsMixin):
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(max_length=254, blank=True, default="", db_index=True)
    full_name = models.CharField(max_length=150)
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.NURSE,
        db_index=True,
    )
    shift = models.CharField(
        max_length=16,
        choices=WorkShift.choices,
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True, db_index=True)
    is_staff = models.BooleanField(default=False)

    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    is_two_factor_enabled = models.BooleanField(default=False)
    totp_secret = models.CharField(max_length=64, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects: ClassVar[UserManager] = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS: ClassVar[list[str]] = ["full_name"]

    class Meta:
        ordering: ClassVar[list[str]] = ["id"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["role", "is_active"], name="user_role_active_idx"),
        ]
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"

    def __str__(self) -> str:
        return f"{self.full_name} ({self.username})"

    @property
    def is_temporarily_locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > timezone.now())


class ShiftAssignment(models.Model):
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="shift_assignments")
    crib = models.ForeignKey(
        "devices.Crib", on_delete=models.PROTECT, related_name="shift_assignments"
    )
    date = models.DateField()
    shift = models.CharField(max_length=16, choices=WorkShift.choices)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_shift_assignments"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-date", "shift", "crib__code", "id"]
        constraints: ClassVar[list[models.UniqueConstraint]] = [
            models.UniqueConstraint(
                fields=["user", "crib", "date", "shift"],
                name="shift_assignment_unique",
            ),
        ]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["date", "shift"], name="shift_assignment_date_idx"),
        ]
        verbose_name = "Asignación de Turno"
        verbose_name_plural = "Asignaciones de Turno"

    def __str__(self) -> str:
        return f"{self.user_id} en cuna {self.crib_id} ({self.date} {self.shift})"
