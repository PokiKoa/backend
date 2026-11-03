from datetime import timedelta
from typing import Any

from django.contrib.auth.password_validation import validate_password
from django.db import models, transaction
from django.utils import timezone
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken

from audit.models import AuditAction
from audit.services import record_audit_event
from poki_koa.exceptions import (
    AccountLockedError,
    AuthenticationDomainError,
    ConflictDomainError,
    DomainError,
)

from .models import User, UserRole, WorkShift
from .totp import build_provisioning_uri, generate_totp_secret, verify_totp_code

MAX_FAILED_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=15)


def _issue_tokens_for_user(user: User) -> dict[str, str]:
    refresh = RefreshToken.for_user(user)
    refresh["role"] = user.role
    refresh["username"] = user.username
    refresh["email"] = user.email
    refresh["full_name"] = user.full_name
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


def _register_failed_attempt(user: User, ip_address: str | None) -> bool:
    """Incrementa el contador de fallos y persiste el bloqueo si alcanza el umbral.

    Retorna True si la cuenta quedó bloqueada en este intento.
    """
    user.failed_login_attempts += 1
    if user.failed_login_attempts >= MAX_FAILED_LOGIN_ATTEMPTS:
        user.locked_until = timezone.now() + LOCKOUT_DURATION
        user.save(update_fields=["failed_login_attempts", "locked_until", "updated_at"])
        record_audit_event(
            action=AuditAction.ACCOUNT_LOCKED,
            resource_type="user",
            resource_id=user.id,
            actor_user=user,
            changed_fields=["failed_login_attempts", "locked_until"],
            ip_address=ip_address,
        )
        return True

    user.save(update_fields=["failed_login_attempts", "updated_at"])
    record_audit_event(
        action=AuditAction.LOGIN_FAILED,
        resource_type="user",
        resource_id=user.id,
        actor_user=user,
        changed_fields=["failed_login_attempts"],
        ip_address=ip_address,
    )
    return False


def authenticate_user(
    *,
    username: str | None = None,
    email: str | None = None,
    password: str,
    otp_code: str | None = None,
    ip_address: str | None = None,
) -> dict[str, Any]:
    identifier = (username or email or "").strip().lower()
    if not identifier or not password:
        raise DomainError("Debe proporcionar usuario y contraseña.")

    auth_error: DomainError | None = None
    tokens: dict[str, str] = {}

    # Se persiste el contador de fallos y la auditoría dentro de la transacción
    # y se lanza la excepción fuera del bloque atomic para no revertir el registro
    with transaction.atomic():
        user = (
            User.objects.select_for_update()
            .filter(models.Q(username=identifier) | models.Q(email=identifier))
            .first()
        )
        if user is None:
            record_audit_event(
                action=AuditAction.LOGIN_FAILED,
                resource_type="auth",
                ip_address=ip_address,
            )
            auth_error = AuthenticationDomainError(
                "Usuario o contraseña incorrectos."
            )
        elif user.is_temporarily_locked:
            record_audit_event(
                action=AuditAction.LOGIN_FAILED,
                resource_type="user",
                resource_id=user.id,
                actor_user=user,
                ip_address=ip_address,
            )
            auth_error = AccountLockedError()
        elif not user.is_active:
            record_audit_event(
                action=AuditAction.LOGIN_FAILED,
                resource_type="user",
                resource_id=user.id,
                actor_user=user,
                ip_address=ip_address,
            )
            auth_error = AuthenticationDomainError(
                "La cuenta de usuario se encuentra desactivada.",
                code="account_inactive",
            )
        elif not user.check_password(password):
            locked_now = _register_failed_attempt(user, ip_address)
            auth_error = (
                AccountLockedError()
                if locked_now
                else AuthenticationDomainError(
                    "Usuario o contraseña incorrectos."
                )
            )
        elif user.is_two_factor_enabled:
            if not otp_code:
                auth_error = AuthenticationDomainError(
                    "Se requiere el código de verificación de dos factores (2FA).",
                    code="two_factor_required",
                )
            elif not verify_totp_code(user.totp_secret, otp_code):
                locked_now = _register_failed_attempt(user, ip_address)
                auth_error = (
                    AccountLockedError()
                    if locked_now
                    else AuthenticationDomainError(
                        "El código de verificación 2FA es inválido.",
                        code="invalid_two_factor_code",
                    )
                )

        if auth_error is None and user is not None:
            user.failed_login_attempts = 0
            user.locked_until = None
            user.last_login = timezone.now()
            user.save(
                update_fields=[
                    "failed_login_attempts",
                    "locked_until",
                    "last_login",
                    "updated_at",
                ]
            )
            tokens = _issue_tokens_for_user(user)
            record_audit_event(
                action=AuditAction.LOGIN_SUCCESS,
                resource_type="user",
                resource_id=user.id,
                actor_user=user,
                ip_address=ip_address,
            )

    if auth_error is not None:
        raise auth_error

    return {
        "access": tokens["access"],
        "refresh": tokens["refresh"],
        "user": user,
    }


def rotate_refresh_token(*, refresh_token_str: str) -> dict[str, str]:
    if not refresh_token_str or not isinstance(refresh_token_str, str):
        raise DomainError("El token de refresco es obligatorio.")

    try:
        old_refresh = RefreshToken(refresh_token_str)
        user_id = old_refresh.get("user_id")
    except TokenError as exc:
        raise AuthenticationDomainError(
            "El token de refresco es inválido o ya fue revocado.",
            code="token_invalid",
        ) from exc

    user = User.objects.filter(id=user_id).first()
    if user is None or not user.is_active:
        try:
            old_refresh.blacklist()
        except TokenError:
            pass
        raise AuthenticationDomainError(
            "La cuenta asociada al token no se encuentra activa.",
            code="account_inactive",
        )

    try:
        old_refresh.blacklist()
    except TokenError as exc:
        raise AuthenticationDomainError(
            "El token de refresco ya fue utilizado o revocado.",
            code="token_revoked",
        ) from exc

    return _issue_tokens_for_user(user)


def logout_user(
    *,
    refresh_token_str: str,
    actor: User,
    ip_address: str | None = None,
) -> None:
    if not refresh_token_str or not isinstance(refresh_token_str, str):
        raise DomainError("El token de refresco es obligatorio para cerrar sesión.")

    try:
        refresh = RefreshToken(refresh_token_str)
    except TokenError as exc:
        raise AuthenticationDomainError(
            "El token de refresco es inválido o ya fue revocado.",
            code="token_invalid",
        ) from exc

    token_user_id = refresh.get("user_id")
    if str(token_user_id) != str(actor.id):
        raise AuthenticationDomainError(
            "El token de refresco no pertenece al usuario autenticado.",
            code="token_owner_mismatch",
        )

    try:
        refresh.blacklist()
    except TokenError as exc:
        raise AuthenticationDomainError(
            "El token de refresco ya fue revocado previamente.",
            code="token_revoked",
        ) from exc

    record_audit_event(
        action=AuditAction.LOGOUT,
        resource_type="user",
        resource_id=actor.id,
        actor_user=actor,
        ip_address=ip_address,
    )


def change_own_password(
    *,
    user: User,
    current_password: str,
    new_password: str,
    ip_address: str | None = None,
) -> dict[str, str]:
    if not user.check_password(current_password or ""):
        # 400 y no 401: un 401 haría que el frontend cierre la sesión por un error de tipeo
        raise DomainError(
            "La contraseña actual no es correcta.",
            details={"current_password": ["La contraseña actual no es correcta."]},
        )
    if current_password == new_password:
        raise DomainError(
            "La nueva contraseña debe ser distinta de la actual.",
            details={"new_password": ["Debe ser distinta de la contraseña actual."]},
        )
    validate_password(new_password, user=user)

    with transaction.atomic():
        user.set_password(new_password)
        user.save(update_fields=["password", "updated_at"])
        # Cambiar la contraseña cierra las demás sesiones: revoca todos los refresh vigentes
        pending = OutstandingToken.objects.filter(user=user).exclude(
            id__in=BlacklistedToken.objects.values("token_id")
        )
        BlacklistedToken.objects.bulk_create(
            [BlacklistedToken(token=token) for token in pending], ignore_conflicts=True
        )
        record_audit_event(
            action=AuditAction.UPDATE,
            resource_type="user",
            resource_id=user.id,
            actor_user=user,
            changed_fields=["password"],
            ip_address=ip_address,
        )

    return _issue_tokens_for_user(user)


def setup_two_factor(*, user: User, ip_address: str | None = None) -> dict[str, str]:
    with transaction.atomic():
        if user.is_two_factor_enabled:
            raise ConflictDomainError(
                "El doble factor de autenticación (2FA) ya se encuentra habilitado."
            )
        secret = generate_totp_secret()
        user.totp_secret = secret
        user.save(update_fields=["totp_secret", "updated_at"])
        record_audit_event(
            action=AuditAction.UPDATE,
            resource_type="user",
            resource_id=user.id,
            actor_user=user,
            changed_fields=["totp_secret"],
            ip_address=ip_address,
        )
    return {
        "secret": secret,
        "provisioning_uri": build_provisioning_uri(
            secret=secret, email=user.email or user.username
        ),
    }


def enable_two_factor(
    *,
    user: User,
    otp_code: str,
    ip_address: str | None = None,
) -> User:
    if not user.totp_secret:
        raise DomainError("Debe configurar primero el secreto TOTP antes de activar 2FA.")
    if not verify_totp_code(user.totp_secret, otp_code):
        raise DomainError(
            "El código TOTP proporcionado es inválido.",
            code="invalid_two_factor_code",
        )

    with transaction.atomic():
        user.is_two_factor_enabled = True
        user.save(update_fields=["is_two_factor_enabled", "updated_at"])
        record_audit_event(
            action=AuditAction.UPDATE,
            resource_type="user",
            resource_id=user.id,
            actor_user=user,
            changed_fields=["is_two_factor_enabled"],
            ip_address=ip_address,
        )
    return user


def disable_two_factor(
    *,
    user: User,
    otp_code: str,
    ip_address: str | None = None,
) -> User:
    if not user.is_two_factor_enabled:
        raise ConflictDomainError("El doble factor de autenticación (2FA) no está activo.")
    if not verify_totp_code(user.totp_secret, otp_code):
        raise DomainError(
            "El código TOTP proporcionado es inválido.",
            code="invalid_two_factor_code",
        )

    with transaction.atomic():
        user.is_two_factor_enabled = False
        user.totp_secret = ""
        user.save(update_fields=["is_two_factor_enabled", "totp_secret", "updated_at"])
        record_audit_event(
            action=AuditAction.UPDATE,
            resource_type="user",
            resource_id=user.id,
            actor_user=user,
            changed_fields=["is_two_factor_enabled", "totp_secret"],
            ip_address=ip_address,
        )
    return user


def create_user_by_admin(
    *,
    actor: User,
    username: str | None = None,
    email: str = "",
    full_name: str,
    password: str,
    role: str = UserRole.NURSE,
    shift: str | None = None,
    is_active: bool = True,
    ip_address: str | None = None,
) -> User:
    normalized_email = (email or "").strip().lower()
    normalized_username = (username or "").strip().lower()
    if not normalized_username and normalized_email:
        normalized_username = normalized_email.split("@")[0]

    if not normalized_username:
        raise DomainError("El nombre de usuario es obligatorio.")
    if not full_name or not full_name.strip():
        raise DomainError("El nombre completo es obligatorio.")
    if role not in set(UserRole.values):
        raise DomainError("El rol especificado no es válido.")
    if shift and shift not in set(WorkShift.values):
        raise DomainError("El turno especificado no es válido.")

    with transaction.atomic():
        if User.objects.filter(username=normalized_username).exists():
            raise ConflictDomainError(
                "Ya existe un usuario registrado con ese nombre de usuario."
            )
        if normalized_email and User.objects.filter(email=normalized_email).exists():
            raise ConflictDomainError(
                "Ya existe un usuario registrado con ese correo electrónico."
            )

        candidate = User(
            username=normalized_username,
            email=normalized_email,
            full_name=full_name.strip(),
            role=role,
            shift=shift or None,
            is_active=is_active,
            is_staff=(role == UserRole.ADMIN),
        )
        validate_password(password, user=candidate)
        candidate.set_password(password)
        candidate.save()

        record_audit_event(
            action=AuditAction.CREATE,
            resource_type="user",
            resource_id=candidate.id,
            actor_user=actor,
            changed_fields=["username", "email", "full_name", "role", "shift", "is_active"],
            ip_address=ip_address,
        )
    return candidate


def update_user_by_admin(
    *,
    actor: User,
    target_user: User,
    data: dict[str, Any],
    ip_address: str | None = None,
) -> User:
    with transaction.atomic():
        locked_target = User.objects.select_for_update().get(pk=target_user.pk)
        changed_fields: list[str] = []

        if locked_target.id == actor.id:
            if "is_active" in data and data["is_active"] is False:
                raise ConflictDomainError(
                    "Un administrador no puede desactivar su propia cuenta."
                )
            if "role" in data and data["role"] != UserRole.ADMIN:
                raise ConflictDomainError(
                    "Un administrador no puede revocar su propio rol administrativo."
                )

        if "username" in data:
            new_username = str(data["username"]).strip().lower()
            if not new_username:
                raise DomainError("El nombre de usuario no puede estar vacío.")
            if new_username != locked_target.username:
                if (
                    User.objects.filter(username=new_username)
                    .exclude(pk=locked_target.pk)
                    .exists()
                ):
                    raise ConflictDomainError(
                        "Ya existe otro usuario con ese nombre de usuario."
                    )
                locked_target.username = new_username
                changed_fields.append("username")

        if "email" in data:
            new_email = str(data["email"] or "").strip().lower()
            if new_email != locked_target.email:
                if (
                    new_email
                    and User.objects.filter(email=new_email)
                    .exclude(pk=locked_target.pk)
                    .exists()
                ):
                    raise ConflictDomainError(
                        "Ya existe otro usuario con ese correo electrónico."
                    )
                locked_target.email = new_email
                changed_fields.append("email")

        if "full_name" in data:
            new_name = str(data["full_name"]).strip()
            if not new_name:
                raise DomainError("El nombre completo no puede estar vacío.")
            if new_name != locked_target.full_name:
                locked_target.full_name = new_name
                changed_fields.append("full_name")

        if "role" in data:
            new_role = data["role"]
            if new_role not in set(UserRole.values):
                raise DomainError("El rol especificado no es válido.")
            if new_role != locked_target.role:
                locked_target.role = new_role
                locked_target.is_staff = new_role == UserRole.ADMIN
                changed_fields.append("role")

        if "shift" in data:
            new_shift = data["shift"] or None
            if new_shift and new_shift not in set(WorkShift.values):
                raise DomainError("El turno especificado no es válido.")
            if new_shift != locked_target.shift:
                locked_target.shift = new_shift
                changed_fields.append("shift")

        if "is_active" in data:
            new_active = bool(data["is_active"])
            if new_active != locked_target.is_active:
                locked_target.is_active = new_active
                changed_fields.append("is_active")

        if data.get("unlock_account") is True and (
            locked_target.failed_login_attempts > 0 or locked_target.locked_until is not None
        ):
            locked_target.failed_login_attempts = 0
            locked_target.locked_until = None
            changed_fields.extend(["failed_login_attempts", "locked_until"])

        if data.get("password"):
            validate_password(data["password"], user=locked_target)
            locked_target.set_password(data["password"])
            changed_fields.append("password")

        if changed_fields:
            locked_target.save()
            record_audit_event(
                action=AuditAction.UPDATE,
                resource_type="user",
                resource_id=locked_target.id,
                actor_user=actor,
                changed_fields=changed_fields,
                ip_address=ip_address,
            )

    return locked_target
