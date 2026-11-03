# Referencia de API REST y WebSockets — Poki Koa

Todas las rutas HTTP del backend están versionadas bajo `/api/v1/` con identificadores y campos JSON en **inglés** y mensajes de error orientados al usuario en **español** (`es-cl`).

- **Esquema OpenAPI 3.0:** `GET /api/v1/schema/`
- **Documentación interactiva (Swagger UI):** `GET /api/v1/docs/`
- **Diagnóstico del sistema:** `GET /api/v1/health/`

---

## 1. Convenciones Generales

### 1.1 Formato uniforme de errores
Cualquier error de validación, dominio, permisos o autenticación responde con la misma envoltura JSON:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Los datos de telemetría enviados no superaron la validación fisiológica.",
    "details": {
      "heart_rate": ["La frecuencia cardíaca debe estar entre 1 y 260 lpm."]
    }
  }
}
```

### 1.2 Paginación, filtrado y ordenamiento
Los listados utilizan paginación estándar (`page_size = 20`, configurable mediante `?page_size=` hasta `100`):

```json
{
  "count": 42,
  "next": "http://localhost:8000/api/v1/patients/?page=2",
  "previous": null,
  "results": []
}
```

Todos los listados aceptan además `?search=` (búsqueda textual) y `?ordering=` (por ejemplo `?ordering=-triggered_at`). Las fechas se envían en formato ISO 8601 (`2026-11-03T08:00:00-03:00`); un valor inválido responde `400`.

### 1.3 Filtros avanzados por recurso

| Recurso | Parámetro | Efecto |
|---|---|---|
| `/api/v1/alerts/` | `is_open=true` / `false` | `true`: alertas `active` + `acknowledged`; `false`: solo `resolved`. |
| | `triggered_after`, `triggered_before` | Ventana temporal sobre `triggered_at`. |
| | `status`, `severity`, `alert_type`, `crib`, `patient` | Filtros exactos. |
| `/api/v1/patients/` | `admitted_after`, `admitted_before` | Ventana temporal sobre `admitted_at`. |
| | `min_weight_g`, `max_weight_g` | Rango inclusivo sobre `current_weight_g`. |
| | `status`, `sex`, `attending_physician`, `crib` | Filtros exactos. |
| `/api/v1/vitals/` y `.../vitals/` de paciente o cuna | `recorded_after`, `recorded_before` | Ventana temporal sobre `recorded_at`. |
| `/api/v1/medication-catalog/` | `low_stock=true` / `false` | `true`: `stock <= min_stock_alert`; `false`: stock suficiente. |
| `/api/v1/audit-logs/` | `timestamp_after`, `timestamp_before` | Ventana temporal sobre `timestamp`. |

Ejemplo: alertas abiertas de las últimas 6 horas de una cuna, más recientes primero:

```
GET /api/v1/alerts/?is_open=true&crib=3&triggered_after=2026-11-03T03:00:00-03:00&ordering=-triggered_at
```

---

## 2. Endpoints REST (`/api/v1/`)

| Módulo | Método y Ruta | Descripción |
|---|---|---|
| **Sistema** | `GET /api/v1/health/` | Estado operativo de base de datos, canal de tiempo real y métricas. |
| **Autenticación** | `POST /api/v1/auth/login/` | Inicio de sesión por `username` y `password` (y `otp_code` si 2FA está activo). |
| | `POST /api/v1/auth/refresh/` | Rotación de token de acceso y refresco. |
| | `POST /api/v1/auth/logout/` | Revocación inmediata del refresh token en lista negra. |
| | `GET /api/v1/auth/me/` | Perfil del usuario autenticado. |
| | `POST /api/v1/auth/change-password/` | Cambio de contraseña del usuario actual. |
| | `POST /api/v1/auth/2fa/setup/` · `enable/` · `disable/` | Configuración, activación y desactivación de segundo factor TOTP. |
| **Usuarios** | `GET, POST /api/v1/users/` | Listado y creación de cuentas de personal (`admin`). |
| | `GET, PUT, PATCH /api/v1/users/{id}/` | Detalle y actualización de rol, turno o estado activo (`admin`). |
| **Pacientes** | `GET, POST /api/v1/patients/` | Listado y admisión clínica de recién nacidos. |
| | `GET, PUT, PATCH /api/v1/patients/{id}/` | Ficha clínica (audita lecturas y restringe campos médicos por rol). |
| | `POST /api/v1/patients/{id}/discharge/` | Egreso lógico conservando historial y liberando la cuna asignada. |
| | `GET, POST /api/v1/patients/{id}/weights/` | Historial de evolución ponderal y registro de nuevo peso en gramos. |
| | `GET /api/v1/patients/{id}/vitals/` | Serie histórica de signos vitales del paciente. |
| | `GET, PUT, PATCH /api/v1/patients/{id}/alert-thresholds/` | Umbrales de alerta personalizados del paciente. |
| **Cuidados** | `GET, POST, PATCH /api/v1/care-plans/` | Planes de cuidado neonatal por área e intervención. |
| | `GET, POST /api/v1/observations/` | Observaciones clínicas categorizadas con firma de autor. |
| **Cunas / IoT** | `GET, POST, PATCH /api/v1/cribs/` | Gestión de cunas e incubadoras de la unidad. |
| | `POST /api/v1/cribs/{id}/assign-patient/` | Asignación transaccional de un paciente activo a la cuna. |
| | `POST /api/v1/cribs/{id}/release/` | Liberación de cuna ocupada. |
| | `POST /api/v1/cribs/{id}/rotate-key/` | Rotación de credencial IoT de la cuna (`admin`). |
| | `POST /api/v1/cribs/check-offline/` | Detecta cunas sin telemetría reciente, las marca `offline` y emite alertas (`sensor_fault`). |
| | `POST /api/v1/cribs/{id}/telemetry/` | Ingesta de lectura de signos vitales (vía `X-Device-Api-Key` o personal autorizado). |
| **Signos Vitales** | `GET /api/v1/vitals/` | Consulta filtrable de lecturas históricas de telemetría. |
| **Alertas** | `GET /api/v1/alerts/` | Listado de alertas clínicas y técnicas. |
| | `POST /api/v1/alerts/{id}/acknowledge/` | Reconocimiento (`acknowledge`) de una alerta activa. |
| | `POST /api/v1/alerts/{id}/resolve/` | Resolución manual de una alerta. |
| | `GET, PUT, PATCH /api/v1/alert-thresholds/default/` | Umbrales fisiológicos globales por defecto. |
| **Farmacia** | `GET, POST, PATCH /api/v1/medication-catalog/` | Catálogo de medicamentos y gestión de stock (`pharmacist` / `admin`). |
| | `GET, POST /api/v1/prescriptions/` | Indicaciones médicas vinculadas al catálogo. |
| | `POST /api/v1/prescriptions/{id}/administer/` | Administración atómica con descuento de stock sin doble aplicación. |
| | `POST /api/v1/prescriptions/{id}/cancel/` | Cancelación de indicación pendiente (`neonatologist`). |
| **Auditoría** | `GET /api/v1/audit-logs/` | Registro inmutable de eventos clínicos y de seguridad (`admin`). |

---

## 3. Canales WebSocket en Tiempo Real (`/ws/v1/`)

Las conexiones WebSocket requieren autenticación mediante token JWT en el query string (`?token=<access_token>`) o sesión activa, y autorizan únicamente a roles clínicos/administrativos (`admin`, `neonatologist`, `nurse`).

| Ruta WebSocket | Eventos emitidos |
|---|---|
| `ws/v1/cribs/{crib_id}/` | `telemetry.reading` (lectura + alertas activas/autorresueltas), `alert.acknowledged`, `alert.resolved`. |
| `ws/v1/patients/{patient_id}/` | `telemetry.reading`, `alert.acknowledged`, `alert.resolved` del paciente indicado. |
| `ws/v1/alerts/` | Flujo global de telemetría y alertas de toda la unidad neonatal. |
