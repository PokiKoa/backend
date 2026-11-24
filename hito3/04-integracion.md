# 04 · Integración y verificación del flujo principal

**Flujo elegido:** un neonatólogo inicia sesión y da el egreso de un paciente; el sistema valida el rol, bloquea al paciente, guarda y audita.

## 1. Diagrama

```mermaid
flowchart LR
    UI["Frontend React<br/>(navegador)"] -->|"POST /auth/login<br/>JSON → JWT"| V
    UI -->|"POST /patients/{id}/discharge<br/>Bearer JWT + {outcome}"| V
    subgraph Backend["Backend Django (propio)"]
        V["views.py + serializers.py<br/>valida formato"] --> S["patients/services.py<br/>discharge_patient"]
        S --> R["accounts/roles.py<br/>require_role"]
        S --> L["patients/locks.py<br/>lock_active_patient"]
        S --> A["audit/services.py<br/>AuditLog sin PHI"]
        S --> RT["vitals/realtime.py<br/>difusión de eventos"]
        EH["poki_koa/exceptions.py<br/>manejador global de errores"]
    end
    L -->|"SELECT … FOR UPDATE"| PG[("PostgreSQL 16")]
    S -->|"ORM"| PG
    RT -->|"group_send"| RD[("Redis 7")]
    ENV[".env<br/>SECRET_KEY, DATABASE_URL, REDIS_URL"] -.-> Backend
    S -. "DomainError" .-> EH
    V -. "ValidationError" .-> EH
    EH -->|"{error:{code,message,details}}"| UI
```

| Participante | Tipo | Datos que intercambia |
|---|---|---|
| `views.py`/`serializers.py` | Propio | JSON, JWT |
| `services.py`, `roles.py`, `locks.py`, `audit/services.py` | Propio | Objetos de dominio, nombres de campos modificados |
| PostgreSQL 16 | Externo | Filas vía ORM, bloqueos de fila |
| Redis 7 | Externo | Eventos de signos vitales y alertas |
| `.env` | Recurso del entorno | `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL` |

## 2. Cómo se manejan los errores en cada conexión

| Conexión | Fallo | Respuesta |
|---|---|---|
| Cliente → vista | Datos inválidos | `400 validation_error` con `details` por campo |
| Cliente → vista | Sin token / token inválido | `401` |
| Vista → servicio | Rol no permitido | `403 permission_denied` |
| Servicio → BD | Paciente inexistente / ya egresado | `404 not_found` / `409 conflict` |
| Salud del sistema | PostgreSQL caído | `GET /api/v1/health/ready/` → `503 {"status":"unavailable"}` |
| WebSocket | Sin token / rol / cuna inexistente | cierres `4401` / `4403` / `4404` |
| Servicio → Redis | Redis caído | **Por lectura de código, no ejecutado:** `group_send` no tiene `try/except` en `vitals/realtime.py`, la telemetría respondería 500. Registrado como deuda ([01 §6](01-diagnostico-e-intervenciones.md)). `health/ready` no mide Redis (responde 200). |

## 3. Tres casos ejecutados

**Entorno (igual en los tres):** 2026-11-23 · Linux (Fedora) · Python 3.12 con `uv` · PostgreSQL 16-alpine y Redis 7-alpine reales en Docker · `uvicorn poki_koa.asgi:application` · backend commit `38aab4b`+ · datos de `seed_demo` (usuarios `dr.soto` y `matrona.diaz`, clave `Clinica#2026`; paciente 1 `active`).

Preparación común:

```bash
export DATABASE_URL=postgres://poki_koa:h3pass@127.0.0.1:55432/poki_koa REDIS_URL=redis://127.0.0.1:56379/0
uv run poki_koa migrate && uv run poki_koa seed_demo
uv run python -m uvicorn poki_koa.asgi:application --app-dir src --port 8123
B=http://127.0.0.1:8123/api/v1     # T1 = JWT de dr.soto, T2 = JWT de matrona.diaz (POST $B/auth/login/)
```

### Caso 1 · Datos válidos

| | |
|---|---|
| Pasos | `curl -X POST $B/patients/1/discharge/ -H "Authorization: Bearer $T1" -H 'Content-Type: application/json' -d '{"outcome":"survived"}'` y después `GET $B/patients/1/` |
| Esperado | `200`; el paciente queda `discharged` con `discharge_outcome: survived`; se escribe un `AuditLog` sin datos clínicos |
| **Obtenido** | `200 OK`. Respuesta: `"id":1,"medical_record_number":"RN-2026-001",…,"status":"discharged","discharge_outcome":"survived"`. Lectura posterior: `estado: discharged survived` |
| Extra | Repetir el egreso → `409 {"code":"conflict","message":"El paciente ya fue egresado previamente."}` |

### Caso 2 · Datos inválidos

| | |
|---|---|
| Pasos (2a) | Mismo `POST` con el token de **`matrona.diaz`** |
| Esperado | `403 permission_denied` y el paciente sin cambios |
| **Obtenido** | `403` — `{"error":{"code":"permission_denied","message":"Solo un Neonatólogo está autorizado para firmar el egreso clínico de un paciente.","details":{}}}`. Estado conservado: `active None` |
| Pasos (2b) | `POST` con `dr.soto` y `{"outcome":"xx"}` |
| Esperado / **Obtenido** | `400 validation_error`; `{"details":{"outcome":["\"xx\" no es una elección válida."]}}`. Estado conservado: `active None` |

### Caso 3 · Recurso ausente

| | |
|---|---|
| Pasos (3a) | `GET $B/patients/999999/` con sesión válida |
| Esperado | `404 not_found`; ningún registro creado |
| **Obtenido** | `404` — `{"error":{"code":"not_found","message":"El recurso solicitado no existe.","details":{}}}` |
| Pasos (3b) | Detener PostgreSQL y llamar `GET $B/health/ready/` |
| Esperado / **Obtenido** | Antes: `200 {"status": "ok"}`. Con la BD detenida: `503 {"status": "unavailable"}` |

> **Fallo corregido durante la verificación:** en la primera ejecución el 404 devolvía `code: "api_error"`. Se arregló en `38aab4b` (ver [01 §5](01-diagnostico-e-intervenciones.md)) y se repitió el caso; la tabla muestra el resultado ya corregido.

**Qué no se simuló:** ningún servicio externo. Quedó sin ejecutar Redis caído con telemetría real (ver §2).

## 4. Suite, cobertura y CI

Ver [05-entrega.md §3](05-entrega.md).
