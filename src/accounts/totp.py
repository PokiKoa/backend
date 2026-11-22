"""Implementación TOTP (RFC 6238) para la verificación en dos pasos, sin dependencias externas."""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote


def generate_totp_secret() -> str:
    """Genera un secreto criptográfico aleatorio de 160 bits codificado en Base32 (sin caracteres de relleno).

    Returns:
        str: El secreto Base32 listo para ser almacenado y asociado a la cuenta del usuario.
    """
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def generate_totp_code(
    secret: str,
    *,
    timestamp: int | None = None,
    step_seconds: int = 30,
    digits: int = 6,
) -> str:
    """Calcula el código TOTP numérico correspondiente a un instante temporal dado.

    Args:
        secret: Secreto Base32 del usuario.
        timestamp: Instante de tiempo UNIX (por defecto, utiliza el tiempo actual).
        step_seconds: Duración de cada ventana temporal en segundos (por defecto 30).
        digits: Longitud del código numérico generado (por defecto 6).

    Returns:
        str: Código numérico TOTP con ceros a la izquierda si es necesario.

    Raises:
        ValueError: Si el secreto proporcionado se encuentra vacío.
    """
    if not secret:
        raise ValueError("El secreto TOTP no puede estar vacío.")
    normalized = secret.strip().upper().replace(" ", "")
    padding = "=" * ((8 - len(normalized) % 8) % 8)
    key = base64.b32decode(normalized + padding, casefold=True)

    current_time = int(time.time()) if timestamp is None else int(timestamp)
    counter = current_time // step_seconds
    counter_bytes = struct.pack(">Q", counter)

    digest = hmac.new(key, counter_bytes, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary_code = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    otp = binary_code % (10**digits)
    return str(otp).zfill(digits)


def verify_totp_code(
    secret: str,
    code: str | None,
    *,
    timestamp: int | None = None,
    window: int = 1,
    step_seconds: int = 30,
) -> bool:
    """Verifica la validez de un código TOTP ingresado, tolerando desfases de reloj
    mediante una ventana de tolerancia configurable.

    Args:
        secret: Secreto Base32 del usuario.
        code: Código de 6 dígitos ingresado por el usuario.
        timestamp: Instante de tiempo UNIX de referencia (por defecto, el momento actual).
        window: Número de ventanas de tolerancia a cada lado del instante actual (por defecto 1).
        step_seconds: Duración de cada ventana temporal en segundos.

    Returns:
        bool: ``True`` si el código coincide dentro de la ventana permitida;
        ``False`` en caso contrario, incluyendo entradas vacías o mal formadas.
    """
    if not secret or not code or not isinstance(code, str):
        return False
    cleaned_code = code.strip()
    if len(cleaned_code) != 6 or not cleaned_code.isdigit():
        return False

    base_ts = int(time.time()) if timestamp is None else int(timestamp)
    for offset in range(-window, window + 1):
        expected = generate_totp_code(
            secret,
            timestamp=base_ts + offset * step_seconds,
            step_seconds=step_seconds,
        )
        if hmac.compare_digest(expected, cleaned_code):
            return True
    return False


def build_provisioning_uri(*, secret: str, email: str, issuer: str = "PokiKoa") -> str:
    """Arma la URI con el esquema ``otpauth://`` optimizada para ser convertida
    a código QR y escaneada por aplicaciones autenticadoras (ej. Google Authenticator).

    Args:
        secret: Secreto Base32 del usuario.
        email: Cuenta o correo electrónico que se muestra en la aplicación.
        issuer: Nombre comercial o del emisor del servicio (por defecto "PokiKoa").

    Returns:
        str: URI completa de aprovisionamiento.
    """
    label = quote(f"{issuer}:{email}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}& digits=6&period=30".replace(
        "& digits=6", "&digits=6"
    )
