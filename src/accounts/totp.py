import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def generate_totp_code(
    secret: str,
    *,
    timestamp: int | None = None,
    step_seconds: int = 30,
    digits: int = 6,
) -> str:
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
    label = quote(f"{issuer}:{email}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}& digits=6&period=30".replace(
        "& digits=6", "&digits=6"
    )
