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


class UserManager(BaseUserManager["User"]):
    def create_user(
        self,
        email: str,
        full_name: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> "User":
        if not email or not email.strip():
            raise ValueError("El correo electrónico es obligatorio.")
        if not full_name or not full_name.strip():
            raise ValueError("El nombre completo es obligatorio.")

        normalized_email = self.normalize_email(email.strip()).lower()
        user = self.model(
            email=normalized_email,
            full_name=full_name.strip(),
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
        email: str,
        full_name: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> "User":
        extra_fields.setdefault("role", UserRole.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        return self.create_user(email=email, full_name=full_name, password=password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True, max_length=254)
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

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = ["full_name"]

    class Meta:
        ordering: ClassVar[list[str]] = ["id"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["role", "is_active"], name="user_role_active_idx"),
        ]
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"

    def __str__(self) -> str:
        return f"{self.full_name} ({self.email})"

    @property
    def is_temporarily_locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > timezone.now())
