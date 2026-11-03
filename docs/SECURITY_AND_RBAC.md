# Seguridad, Autenticación y Control de Acceso (RBAC) — Poki Koa

Poki Koa protege los datos clínicos neonatales mediante autenticación diferenciada para personal humano y dispositivos IoT, control de acceso basado en roles (RBAC) a nivel de vista y de campo, y auditoría inmutable sin exposición de información clínica sensible (PHI).

---

## 1. Autenticación de Usuarios Humanos (JWT + Bloqueo + 2FA)

- **Identificador de acceso:** Inicio de sesión mediante `username` y `password` en `POST /api/v1/auth/login/`.
- **Tokens JWT (`djangorestframework-simplejwt`):**
  - `ACCESS_TOKEN_LIFETIME`: 15 minutos.
  - `REFRESH_TOKEN_LIFETIME`: 8 horas (alineado a la duración de un turno clínico).
  - **Rotación y revocación:** `ROTATE_REFRESH_TOKENS = True` y `BLACKLIST_AFTER_ROTATION = True`. Al cerrar sesión (`POST /api/v1/auth/logout/`), el refresh token queda invalidado en la lista negra.
- **Protección contra fuerza bruta:**
  - Política de contraseñas de mínimo 10 caracteres con exigencia de mayúsculas, minúsculas y dígitos (`ClinicalPasswordValidator`).
  - Rate limiting en login (`5/min`).
  - Bloqueo temporal de cuenta (`locked_until` durante 15 minutos) tras 5 intentos fallidos consecutivos (`failed_login_attempts`), registrando cada fallo en `AuditLog`.
- **Segundo Factor de Autenticación (2FA TOTP RFC 6238):**
  - Soportado de forma nativa en el modelo `User` (`totp_secret`, `is_two_factor_enabled`).
  - Es configurable por cuenta (`/api/v1/auth/2fa/setup/`, `/enable/`, `/disable/`): recomendado para cuentas administrativas (`admin`) y opcional para el personal clínico de sala para no introducir fricción durante urgencias neonatales.

---

## 2. Autenticación de Dispositivos / Cunas IoT (`X-Device-Api-Key`)

- Los monitores e incubadoras nunca comparten credenciales de usuarios humanos ni utilizan JWT.
- Cada `Crib` almacena únicamente un prefijo público (`api_key_prefix`) y el hash SHA-256 (`api_key_hash`) de su clave. La clave en texto plano solo se muestra una vez al crear la cuna o al rotarla (`POST /api/v1/cribs/{id}/rotate-api-key/`).
- El endpoint `POST /api/v1/cribs/{id}/telemetry/` valida mediante comparación en tiempo constante (`hmac.compare_digest`) que la cabecera `X-Device-Api-Key` corresponda específicamente a la cuna `{id}` y que `is_device_active=True`.

---

## 3. Matriz de Roles y Permisos (RBAC)

| Recurso / Operación | `admin` | `neonatologist` | `nurse` (Matrona/Enfermera) | `pharmacist` | Dispositivo (`API Key`) |
|---|---|---|---|---|---|
| Gestión de usuarios (`/api/v1/users/`) | CRUD | — | — | — | — |
| Consulta de auditoría (`/api/v1/audit-logs/`) | Lectura | — | — | — | — |
| Cunas: crear/editar/rotar API key | Sí | Lectura | Lectura | Lectura | — |
| Cunas: asignar / liberar paciente | Sí | Sí | Sí | — | — |
| Pacientes: admisión y datos de enfermería | Lectura | Sí | Sí | Lectura | — |
| Pacientes: diagnóstico y médico tratante | Lectura | **Exclusivo** | — | Lectura | — |
| Pacientes: firmar egreso clínico (`discharge`) | — | **Exclusivo** | — | — | — |
| Evolución de peso, planes de cuidado y observaciones | Lectura | CRUD | CRUD | Lectura | — |
| Telemetría: ingesta (`POST .../telemetry/`) | Sí | Sí | Sí | — | **Sí (solo su cuna)** |
| Telemetría: consulta histórica y WebSocket | Sí | Sí | Sí | — | — |
| Alertas: reconocer (`acknowledge`) y resolver | Sí | Sí | Sí | — | — |
| Umbrales de alerta: configurar | Sí | Sí | Lectura | — | — |
| Catálogo de medicamentos y stock | CRUD | Lectura | Lectura | **CRUD + Stock** | — |
| Indicaciones médicas: prescribir / cancelar | Lectura | **Exclusivo** | Lectura | Lectura | — |
| Indicaciones médicas: administrar dosis | — | Sí | Sí | — | — |

---

## 4. Privacidad y Auditoría Clínica (`AuditLog`)

- Toda lectura de ficha de paciente (`retrieve`) y toda mutación sobre entidades clínicas genera un registro en `AuditLog`.
- **Cero datos clínicos en logs:** El campo `changed_fields` guarda exclusivamente los nombres de las columnas modificadas (por ejemplo `["current_weight_g", "crib_id"]`), nunca los valores antes/después ni diagnósticos.
- Los registros de `AuditLog` son inmutables a nivel de modelo (bloquean `save()` de actualización y `delete()`).
