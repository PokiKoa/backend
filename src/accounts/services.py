"""Servicios de cuentas: autenticación JWT, 2FA, gestión de usuarios y turnos de enfermería."""

from datetime import date, datetime, timedelta
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
    NotFoundDomainError,
)

from .models import SHIFT_HOURS, ShiftAssignment, User, UserRole, WorkShift
from .roles import ADMIN_ONLY, require_role
from .totp import build_provisioning_uri, generate_totp_secret, verify_totp_code

MAX_FAILED_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=15)


def _issue_tokens_for_user(user: User) -> dict[str, str]:
    """Genera y emite el par de tokens JWT (access y refresh) con los claims
    personalizados del usuario.

    Args:
        user: Instancia del usuario autenticado.

    Returns:
        dict[str, str]: Diccionario con los tokens 'access' y 'refresh'.
    """
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
    """Incrementa el contador de intentos fallidos de login y persiste el bloqueo
    si se alcanza el umbral máximo permitido.

    Args:
        user: Instancia del usuario que falló el acceso.
        ip_address: Dirección IP de origen de la petición.

    Returns:
        bool: True si la cuenta quedó bloqueada en este intento, False en caso contrario.
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


def _login_error(
    user: User | None, password: str, otp_code: str | None, ip_address: str | None
) -> DomainError | None:
    """Evalúa las credenciales de acceso y retorna el error de dominio correspondiente,
    o None si las credenciales son completamente válidas.

    Args:
        user: Instancia del usuario encontrado o None si no existe.
        password: Contraseña en texto plano ingresada.
        otp_code: Código de doble factor (2FA) opcional.
        ip_address: Dirección IP de origen.

    Returns:
        DomainError | None: Excepción de dominio si falla alguna validación, o None si pasa.
    """
    if user is None:
        record_audit_event(
            action=AuditAction.LOGIN_FAILED, resource_type="auth", ip_address=ip_address
        )
        return AuthenticationDomainError("Usuario o contraseña incorrectos.")
    if user.is_temporarily_locked or not user.is_active:
        record_audit_event(
            action=AuditAction.LOGIN_FAILED,
            resource_type="user",
            resource_id=user.id,
            actor_user=user,
            ip_address=ip_address,
        )
        if user.is_temporarily_locked:
            return AccountLockedError()
        return AuthenticationDomainError(
            "La cuenta de usuario se encuentra desactivada.", code="account_inactive"
        )
    if not user.check_password(password):
        if _register_failed_attempt(user, ip_address):
            return AccountLockedError()
        return AuthenticationDomainError("Usuario o contraseña incorrectos.")
    if user.is_two_factor_enabled:
        if not otp_code:
            return AuthenticationDomainError(
                "Se requiere el código de verificación de dos factores (2FA).",
                code="two_factor_required",
            )
        if not verify_totp_code(user.totp_secret, otp_code):
            if _register_failed_attempt(user, ip_address):
                return AccountLockedError()
            return AuthenticationDomainError(
                "El código de verificación 2FA es inválido.", code="invalid_two_factor_code"
            )
    return None


def authenticate_user(
    *,
    username: str | None = None,
    email: str | None = None,
    password: str,
    otp_code: str | None = None,
    ip_address: str | None = None,
) -> dict[str, Any]:
    """Autentica a un usuario por nombre de usuario o correo y emite el par de tokens JWT.

    Precondiciones:
        - Se debe proporcionar al menos un identificador válido (`username` o `email`) y una contraseña no vacía.
        - El usuario correspondiente debe existir en el sistema y no encontrarse bloqueado temporalmente.
        - Si el usuario tiene activo el doble factor (2FA), se exige un código TOTP válido.
    Postcondiciones:
        - Si la autenticación es exitosa, se restablecen los contadores de fallos de login, se actualiza el último acceso y se emiten los tokens JWT.
        - Se registra un evento de auditoría exitoso o fallido según corresponda.
    Invariante:
        - Ningún usuario bloqueado temporalmente (`locked_until` en el futuro) o inactivo (`is_active=False`) puede obtener un token de acceso.
        - Todo login exitoso retorna obligatoriamente un diccionario con las claves 'access', 'refresh' y 'user'.
    """
    identifier = (username or email or "").strip().lower()
    if not identifier or not password:
        raise DomainError("Debe proporcionar usuario y contraseña.")

    auth_error: DomainError | None = None
    tokens: dict[str, str] = {}

    with transaction.atomic():
        user = (
            User.objects.select_for_update()
            .filter(models.Q(username=identifier) | models.Q(email=identifier))
            .first()
        )
        auth_error = _login_error(user, password, otp_code, ip_address)

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

    assert user is not None, "Invariante roto: Se autenticó un usuario nulo."
    assert user.is_active and not user.is_temporarily_locked, (
        "Invariante roto: Un usuario inactivo o bloqueado obtuvo acceso."
    )
    assert "access" in tokens and "refresh" in tokens, (
        "Invariante roto: La autenticación exitosa no generó los tokens JWT requeridos."
    )

    return {
        "access": tokens["access"],
        "refresh": tokens["refresh"],
        "user": user,
    }


def rotate_refresh_token(*, refresh_token_str: str) -> dict[str, str]:
    """Rota un refresh token: lo revoca en la lista negra y emite un nuevo par de tokens.

    Args:
        refresh_token_str: Cadena del refresh token vigente.

    Returns:
        dict[str, str]: Diccionario con los nuevos 'access' y 'refresh' tokens.

    Raises:
        DomainError: Si el token viene vacío.
        AuthenticationDomainError: Si el token es inválido, expiró, fue revocado o el usuario está inactivo.
    """
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
    """Cierra sesión revocando explícitamente (lista negra) el refresh token del usuario.

    Args:
        refresh_token_str: Cadena del refresh token a revocar.
        actor: Instancia del usuario autenticado que solicita el cierre de sesión.
        ip_address: Dirección IP de origen para auditoría.

    Raises:
        DomainError: Si el token de refresco está vacío.
        AuthenticationDomainError: Si el token es inválido o no pertenece al usuario autenticado.
    """
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
    """Cambia la contraseña del propio usuario autenticado, revoca las sesiones anteriores
    y reemite un nuevo par de tokens.

    Args:
        user: Instancia del usuario autenticado.
        current_password: Contraseña actual en texto plano para confirmar identidad.
        new_password: Nueva contraseña propuesta; debe cumplir los validadores del sistema.
        ip_address: Dirección IP de origen para auditoría.

    Returns:
        dict[str, str]: Nuevo par de tokens 'access' y 'refresh'.

    Raises:
        DomainError: Si la contraseña actual es incorrecta o la nueva contraseña no es válida.
    """
    if not user.check_password(current_password or ""):
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
    """Genera un secreto TOTP temporal pendiente de confirmación para habilitar 2FA.

    Args:
        user: Instancia del usuario que solicita la configuración.
        ip_address: Dirección IP de origen para auditoría.

    Returns:
        dict[str, str]: Diccionario con el secreto y la URI de aprovisionamiento (para código QR).

    Raises:
        ConflictDomainError: Si el doble factor ya se encuentra activo en la cuenta.
    """
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
    """Activa definitivamente el 2FA tras verificar exitosamente un código TOTP
    generado a partir del secreto pendiente.

    Args:
        user: Instancia del usuario.
        otp_code: Código numérico de 6 dígitos de la aplicación autenticadora.
        ip_address: Dirección IP de origen para auditoría.

    Returns:
        User: La instancia del usuario actualizada con el 2FA activo.

    Raises:
        DomainError: Si no hay un secreto configurado previamente o el código TOTP es inválido.
    """
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
    """Desactiva el doble factor de autenticación tras verificar un código TOTP vigente.

    Args:
        user: Instancia del usuario.
        otp_code: Código numérico de 6 dígitos de la aplicación autenticadora.
        ip_address: Dirección IP de origen para auditoría.

    Returns:
        User: La instancia del usuario con el 2FA desactivado y secreto limpiado.

    Raises:
        ConflictDomainError: Si el 2FA no se encuentra activo actualmente.
        DomainError: Si el código TOTP proporcionado es inválido.
    """
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
    """Crea una cuenta de usuario desde el panel de administración.

    Precondiciones:
        - El nombre de usuario (o el correo para derivarlo) y el nombre completo no deben estar vacíos.
        - El `role` y el `shift` (si se provee) deben pertenecer a los valores permitidos por el sistema.
        - No debe existir un usuario previamente registrado con el mismo `username` o `email`.
    Postcondiciones:
        - Se persiste en la base de datos un nuevo registro `User` con la contraseña hasheada.
        - Se registra un evento de auditoría (CREATE) vinculado al administrador que ejecutó la acción.
    Invariante:
        - La contraseña del usuario creado nunca se almacena en texto plano.
        - Si el usuario tiene rol de Administrador, obligatoriamente debe tener permisos de `is_staff`.
    """
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
            raise ConflictDomainError("Ya existe un usuario registrado con ese nombre de usuario.")
        if normalized_email and User.objects.filter(email=normalized_email).exists():
            raise ConflictDomainError("Ya existe un usuario registrado con ese correo electrónico.")

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

    assert candidate.password != password, (
        "Invariante roto: La contraseña se guardó en texto plano."
    )
    assert candidate.is_staff == (candidate.role == UserRole.ADMIN), (
        "Invariante roto: Inconsistencia entre el rol ADMIN y el flag is_staff."
    )

    return candidate


def _check_admin_self_update(actor: User, target: User, data: dict[str, Any]) -> None:
    """Impide que un administrador modifique su propia cuenta para desactivarse
    o quitarse el rol administrativo.

    Args:
        actor: Administrador que ejecuta la acción.
        target: Instancia del usuario que está siendo modificado.
        data: Diccionario con los datos parciales a actualizar.

    Raises:
        ConflictDomainError: Si el admin intenta auto-desactivarse o quitarse los privilegios.
    """
    if target.id != actor.id:
        return
    if data.get("is_active") is False:
        raise ConflictDomainError("Un administrador no puede desactivar su propia cuenta.")
    if "role" in data and data["role"] != UserRole.ADMIN:
        raise ConflictDomainError("Un administrador no puede revocar su propio rol administrativo.")


def _normalize_username(user: User, value: Any) -> str:
    """Normaliza y valida la unicidad del nombre de usuario durante una actualización."""
    username = str(value).strip().lower()
    if not username:
        raise DomainError("El nombre de usuario no puede estar vacío.")
    if (
        username != user.username
        and User.objects.filter(username=username).exclude(pk=user.pk).exists()
    ):
        raise ConflictDomainError("Ya existe otro usuario con ese nombre de usuario.")
    return username


def _normalize_email(user: User, value: Any) -> str:
    """Normaliza y valida la unicidad del correo electrónico durante una actualización."""
    email = str(value or "").strip().lower()
    if (
        email
        and email != user.email
        and User.objects.filter(email=email).exclude(pk=user.pk).exists()
    ):
        raise ConflictDomainError("Ya existe otro usuario con ese correo electrónico.")
    return email


def _normalize_full_name(user: User, value: Any) -> str:
    """Normaliza y valida que el nombre completo no esté vacío."""
    name = str(value).strip()
    if not name:
        raise DomainError("El nombre completo no puede estar vacío.")
    return name


def _normalize_role(user: User, value: Any) -> str:
    """Valida que el rol pertenezca a los valores permitidos del sistema."""
    if value not in set(UserRole.values):
        raise DomainError("El rol especificado no es válido.")
    return value


def _normalize_shift(user: User, value: Any) -> str | None:
    """Valida que el turno pertenezca a los valores permitidos del sistema."""
    shift = value or None
    if shift and shift not in set(WorkShift.values):
        raise DomainError("El turno especificado no es válido.")
    return shift


def _normalize_is_active(user: User, value: Any) -> bool:
    """Normaliza el valor booleano de activación de cuenta."""
    return bool(value)


_ADMIN_EDITABLE_FIELDS = {
    "username": _normalize_username,
    "email": _normalize_email,
    "full_name": _normalize_full_name,
    "role": _normalize_role,
    "shift": _normalize_shift,
    "is_active": _normalize_is_active,
}


def _apply_admin_field_updates(user: User, data: dict[str, Any]) -> list[str]:
    """Valida y asigna en memoria los campos editables enviados por un admin; devuelve los modificados."""
    changed: list[str] = []
    for field, normalize in _ADMIN_EDITABLE_FIELDS.items():
        if field not in data:
            continue
        new_value = normalize(user, data[field])
        if new_value == getattr(user, field):
            continue
        setattr(user, field, new_value)
        changed.append(field)
        if field == "role":
            user.is_staff = new_value == UserRole.ADMIN
    return changed


def _apply_unlock_and_password(user: User, data: dict[str, Any]) -> list[str]:
    """Procesa el desbloqueo manual de cuenta y la actualización de contraseña si se solicitan."""
    changed: list[str] = []
    if data.get("unlock_account") is True and (
        user.failed_login_attempts > 0 or user.locked_until is not None
    ):
        user.failed_login_attempts = 0
        user.locked_until = None
        changed.extend(["failed_login_attempts", "locked_until"])
    if data.get("password"):
        validate_password(data["password"], user=user)
        user.set_password(data["password"])
        changed.append("password")
    return changed


def update_user_by_admin(
    *,
    actor: User,
    target_user: User,
    data: dict[str, Any],
    ip_address: str | None = None,
) -> User:
    """Actualiza parcialmente una cuenta de usuario desde el panel de administración.

    Args:
        actor: Administrador que realiza el cambio.
        target_user: Usuario a modificar; se relee con bloqueo de fila.
        data: Diccionario con los campos a cambiar.
        ip_address: IP de origen para la auditoría.

    Returns:
        User: La instancia del usuario actualizada.

    Raises:
        ConflictDomainError: Auto-desactivación/auto-revocación de rol o duplicados.
        DomainError: Valores vacíos o inválidos.
    """
    with transaction.atomic():
        locked_target = User.objects.select_for_update().get(pk=target_user.pk)
        _check_admin_self_update(actor, locked_target, data)

        changed_fields = [
            *_apply_admin_field_updates(locked_target, data),
            *_apply_unlock_and_password(locked_target, data),
        ]

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


ASSIGNABLE_ROLES = {UserRole.NURSE, UserRole.NEONATOLOGIST}


def shift_window(shift: str, day: date) -> tuple[datetime, datetime]:
    """Calcula el intervalo de tiempo (inicio y fin) de un turno para una fecha determinada.

    Args:
        shift: Identificador del turno (WorkShift).
        day: Fecha de inicio del turno.

    Returns:
        tuple[datetime, datetime]: Tupla con los datetimes de inicio y fin con zona horaria.
    """
    start_time, end_time = SHIFT_HOURS[shift]
    start = timezone.make_aware(datetime.combine(day, start_time))
    end_day = day + timedelta(days=1) if end_time <= start_time else day
    return start, timezone.make_aware(datetime.combine(end_day, end_time))


def current_shift(now: datetime | None = None) -> tuple[date, str]:
    """Determina la fecha de inicio y el tipo de turno vigente en un instante dado.

    Args:
        now: Instante temporal a evaluar (por defecto, el momento actual).

    Returns:
        tuple[date, str]: Tupla con (día_de_inicio, tipo_de_turno).
    """
    local = timezone.localtime(now or timezone.now())
    for shift in WorkShift.values:
        for day in (local.date(), local.date() - timedelta(days=1)):
            start, end = shift_window(shift, day)
            if start <= local < end:
                return day, shift
    raise AssertionError("SHIFT_HOURS debe cubrir las 24 horas")


def create_shift_assignment(
    *,
    actor: User,
    user_id: int,
    crib_id: int,
    day: date,
    shift: str,
    ip_address: str | None = None,
) -> ShiftAssignment:
    """Asigna un profesional a una cuna para un turno y día específico.

    Precondiciones:
        - El `actor` debe tener rol de Administrador.
        - El `shift` debe ser un turno válido (Mañana, Tarde, Noche).
        - El `user_id` debe corresponder a un usuario activo con rol clínico (Neonatólogo o Matrona/Enfermera).
        - El `crib_id` debe corresponder a una cuna existente.
        - No debe existir una asignación previa para este profesional, cuna, día y turno.
    Postcondiciones:
        - Se crea, persiste y retorna un registro `ShiftAssignment`.
        - Se registra un evento de auditoría de creación en el sistema.
    Invariante:
        - La asignación retornada siempre debe pertenecer a un usuario con rol clínico autorizado (NURSE o NEONATOLOGIST).
        - La asignación siempre preserva intactos el día y turno solicitados.
    """
    from devices.models import Crib

    require_role(actor, ADMIN_ONLY, "Solo un administrador puede asignar turnos.")
    if shift not in set(WorkShift.values):
        raise DomainError("El turno especificado no es válido.")

    staff = User.objects.filter(pk=user_id, is_active=True).first()
    if staff is None:
        raise NotFoundDomainError("El profesional indicado no existe o está inactivo.")
    if staff.role not in ASSIGNABLE_ROLES:
        raise DomainError("Solo personal de neonatología o enfermería puede asignarse a cunas.")
    if not Crib.objects.filter(pk=crib_id).exists():
        raise NotFoundDomainError("La cuna indicada no existe.")

    with transaction.atomic():
        if ShiftAssignment.objects.filter(
            user=staff, crib_id=crib_id, date=day, shift=shift
        ).exists():
            raise ConflictDomainError("El profesional ya está asignado a esa cuna en ese turno.")
        assignment = ShiftAssignment.objects.create(
            user=staff, crib_id=crib_id, date=day, shift=shift, created_by=actor
        )
        record_audit_event(
            action=AuditAction.CREATE,
            resource_type="shift_assignment",
            resource_id=assignment.id,
            actor_user=actor,
            changed_fields=["user_id", "crib_id", "date", "shift"],
            ip_address=ip_address,
        )

    assert assignment.user.role in ASSIGNABLE_ROLES, (
        "Invariante roto: Se asignó una cuna a un rol no clínico."
    )
    assert assignment.date == day and assignment.shift == shift, (
        "Invariante roto: La asignación mutó el día o turno original."
    )

    return assignment


def delete_shift_assignment(
    *, actor: User, assignment: ShiftAssignment, ip_address: str | None = None
) -> None:
    """Elimina formalmente una asignación de turno previa.

    Args:
        actor: Administrador que ejecuta la eliminación.
        assignment: Instancia de ShiftAssignment a borrar.
        ip_address: Dirección IP de origen para auditoría.

    Raises:
        PermissionDomainError: Si el actor no posee rol de Administrador.
    """
    require_role(actor, ADMIN_ONLY, "Solo un administrador puede eliminar asignaciones de turno.")
    with transaction.atomic():
        assignment_id = assignment.id
        assignment.delete()
        record_audit_event(
            action=AuditAction.UPDATE,
            resource_type="shift_assignment",
            resource_id=assignment_id,
            actor_user=actor,
            changed_fields=["deleted"],
            ip_address=ip_address,
        )


def assigned_crib_ids(*, user: User, now: datetime | None = None) -> tuple[date, str, list[int]]:
    """Lista los identificadores de las cunas asignadas a un profesional en el turno vigente.

    Args:
        user: Instancia del profesional consultado.
        now: Instante temporal de evaluación (por defecto, ahora).

    Returns:
        tuple[date, str, list[int]]: Tupla conteniendo (fecha_inicio, turno, lista_de_ids_de_cunas).
    """
    day, shift = current_shift(now)
    crib_ids = list(
        ShiftAssignment.objects.filter(user=user, date=day, shift=shift)
        .order_by("crib__code")
        .values_list("crib_id", flat=True)
    )
    return day, shift, crib_ids
