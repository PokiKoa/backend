# Hito 3 — Integración, verificación y entrega

Plantilla para completar los requisitos de las secciones 7 y 8 de la *Guía de evaluación del Hito 3 (ISF224)*.

**Instrucción:** reemplaza todos los marcadores `<<COMPLETAR: ...>>` por datos reales antes de la entrega. No inventes resultados: pega la salida que obtuviste. La ficha de las tres intervenciones está en [../guia-unidad-3.md](../guia-unidad-3.md).

---

## 1. Flujo principal del proyecto

El diagrama de capas ya existe en [../ARCHITECTURE.md#2-capas-y-módulos-del-sistema](../ARCHITECTURE.md). Cópialo o enlázalo en la ficha; no hace falta dibujar otro.

| Participante | Tipo | Qué hace en el flujo | Datos que intercambia |
| --- | --- | --- | --- |
| `views.py` + `serializers.py` | Módulo propio | Recibe REST/WebSocket, valida y delega | JSON, JWT, API Key |
| `services.py` | Módulo propio | Aplica reglas y transacciones | Llamadas a modelos y reglas puras |
| `rules.py`, `policies.py`, `roles.py`, `locks.py` | Módulo propio | Reglas puras y compartidas | Sin E/S |
| `audit/services.py` | Módulo propio | Bitácora sin PHI | Nombres de campos modificados |
| PostgreSQL 16 | Dependencia externa | Persistencia | Filas vía ORM |
| Redis 7 | Dependencia externa | Difusión WebSocket y caché | Eventos de signos vitales |
| `drf-spectacular` 0.30.0 | Dependencia externa | Contrato OpenAPI | `openapi/schema.yml`, `/api/v1/schema/` |
| `.env` / variables de entorno | Recurso del entorno | Configuración sensible | `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, … |

**Manejo de errores en las conexiones** (ya documentado):

- HTTP: `403 permission_denied`, `404 not_found`, `409 conflict` — manejador global en `src/poki_koa/exceptions.py`.
- WebSocket: cierres `4401` (sin token), `4403` (rol no autorizado), `4404` (cuna/paciente inexistente) — ver [../API_REFERENCE.md](../API_REFERENCE.md).
- PostgreSQL no disponible: `GET /api/v1/health/ready/` responde `503 {"status": "unavailable"}` (verificado en `src/poki_koa/views.py`). Redis no disponible: si no hay `channel_layer`, `_send_to_groups` retorna sin enviar; si falla `group_send`, no hay `try/except` en `src/vitals/realtime.py` ni en `record_vital_reading` (`src/vitals/services.py`), por lo que la excepción se propaga y la petición de telemetría respondería 500. **Conclusión por lectura de código; no ejecutado en este entorno.**

---

## 2. Tres casos de integración

Ejecuta el flujo con `seed_demo` cargado. Usuarios de demo: `admin`/`admin2026` y `dr.soto`, `matrona.diaz`, `qf.silva` con `Clinica#2026` (también aceptan su correo `@pokikoa.cl`).

### Caso 1 — Datos válidos

| Campo | Contenido |
| --- | --- |
| Pasos | 1) `POST /api/v1/auth/login/` con `{"username":"dr.soto","password":"Clinica#2026"}`; 2) `POST /api/v1/patients/<id>/discharge/` con `{"outcome":"survived"}` |
| Entorno | 2026-11-22 · Windows · Python 3.12.13 con `uv` · SQLite (dev) y channel layer en memoria · backend `7537a0f` (commit al ejecutar) · frontend `0bd3ee9` |
| Resultado esperado | `200 OK`; el paciente queda con `status: "discharged"` y `discharge_outcome: "survived"` (ver `PatientStatus` en `src/patients/models.py`), y se escribe un `AuditLog` sin datos clínicos |
| Resultado obtenido | `HTTP/1.1 200 OK`. Respuesta real: `{"id":2,"medical_record_number":"RN-2026-002","status":"discharged","discharge_outcome":"survived","discharge_cause":"none","discharged_at":"2026-11-22T00:41:41.270332-03:00","discharged_by":2}`. Verificación con `GET /api/v1/patients/2/`: `status=discharged`, `discharge_outcome=survived`, `discharged_by=2` |

### Caso 2 — Datos inválidos

| Campo | Contenido |
| --- | --- |
| Pasos | 1) login con `{"username":"matrona.diaz","password":"Clinica#2026"}`; 2) el mismo `POST /api/v1/patients/<id>/discharge/` |
| Resultado esperado | `403 permission_denied` con el mensaje «Solo un Neonatólogo está autorizado para firmar el egreso clínico de un paciente.» |
| Resultado obtenido | `HTTP/1.1 403 Forbidden`. Cuerpo real: `{"error":{"code":"permission_denied","message":"Solo un Neonatólogo está autorizado para firmar el egreso clínico de un paciente.","details":{}}}` |
| Estado que conserva el sistema | Sin cambios: paciente 1 con `status="active"` y `discharge_outcome=None`, comprobado en la base con `Patient.objects.get(pk=1)` |

### Caso 3 — Recurso ausente

| Campo | Contenido |
| --- | --- |
| Pasos | Con sesión válida, `GET /api/v1/patients/999999/` (id inexistente). Opcional: detener Redis/PostgreSQL y llamar a `GET /api/v1/health/ready/` |
| Resultado esperado | `404 not_found` (o `503` en el healthcheck); ningún registro nuevo, el sistema sigue operativo |
| Resultado obtenido | `HTTP/1.1 404 Not Found`. Cuerpo real: `{"error":{"code":"api_error","message":"Error en la solicitud.","details":{}}}` |
| Estado que conserva el sistema | No se creó ni modificó ningún registro; `GET /api/v1/health/ready/` sigue respondiendo `200 {"status":"ok"}` |

> No se simuló un servicio externo: se ejecutó con SQLite y channel layer en memoria. Queda pendiente repetir la comprobación con PostgreSQL 16 y Redis 7 (Docker/CI).

---

## 3. Suite, cobertura y CI

```bash
uv run ruff check src
uv run ruff format --check src
uv run poki_koa makemigrations --check
uv run pytest
uv run coverage erase
uv run coverage run -m pytest
uv run coverage report
uv run coverage html
uv run coverage xml
```

Resultado verificado el 2026-11-22: `ruff check src` sin hallazgos, `ruff format --check src` con 132 archivos formateados, `uv run pytest` → **210 passed, 178 subtests passed** (58 advertencias por `staticfiles/` ausente).

| Evidencia | Registro |
| --- | --- |
| Porcentaje total de cobertura | **95,3 %** — `TOTAL 4286 148 792 79 95.3%` (líneas y ramas de `src/`; umbral 90 %) |
| Reporte HTML/XML | Generados localmente en `htmlcov/index.html` y `coverage.xml` (ambos ignorados por Git). Enlace al artefacto de CI: seleccionar `cobertura-backend` en el run de Actions |
| Ejecución de CI (backend) | [Historial de ejecuciones](https://github.com/PokiKoa/backend/actions) — pegar la URL del run de la entrega |
| Ejecución de CI (frontend) | [Historial de ejecuciones](https://github.com/PokiKoa/frontend/actions) — pegar la URL del run de la entrega |

El workflow ya genera el artefacto `cobertura-backend` y falla si la cobertura baja de 90 %: [../../.github/workflows/ci.yml](../../.github/workflows/ci.yml).

---

## 4. Paquete y versión

| Campo | Valor |
| --- | --- |
| Tag propuesto | `2.0.0` — coincide con `version = "2.0.0"` de `pyproject.toml`. Es un cambio mayor respecto a `entrega2`/`0.0.1`: reescritura por aplicaciones de dominio y contrato REST `/api/v1/` nuevo, no compatible con el prototipo v1 |
| Commit backend entregado | El de la rama `desarrollo` que se etiquete como `2.0.0` (tag pendiente de crear) |
| Commit frontend entregado | `0bd3ee9` (rama `desarrollo`, versión integrada). Las intervenciones de la Unidad 3 están en `refactor/unidad-3` (`bb57d46`) y aún no están mergeadas en `desarrollo` |
| Paquete | Imagen Docker + `docker-compose.prod.yml` + `.env.prod.example`; alternativamente ZIP con el código y el README |
| Cómo obtenerlo | `docker compose -f docker-compose.prod.yml up -d --build`, ver [../DEPLOYMENT_AND_OPERATIONS.md](../DEPLOYMENT_AND_OPERATIONS.md) |
| Dependencias declaradas | `uv.lock` (backend) y `package-lock.json` (frontend) |
| Datos ficticios | Comando `uv run poki_koa seed_demo` |
| Configuración de ejemplo | `.env.example` y `.env.prod.example` |
| Avisos de licencia | `drf-spectacular` BSD-3 (documentado en la [ficha §4](../guia-unidad-3.md)); Django, Django REST Framework y Channels BSD-3; React MIT. Pendiente: generar `THIRD_PARTY_LICENSES.md` con los textos completos si se redistribuye el paquete |

### Notas de versión

| Campo | Valor |
| --- | --- |
| Fecha | 2026-11-22 |
| Cambios | Tres intervenciones de la Unidad 3, despliegue en producción, healthcheck `ready`, IP de auditoría y validación del `Origin` de WebSockets |
| Indicaciones de actualización | Desde `entrega2`: `git fetch --tags && git checkout 2.0.0`, `uv sync`, `uv run poki_koa migrate`, `uv run poki_koa seed_demo` |
| Limitaciones conocidas | Ver [../guia-unidad-3.md#6-deuda-pendiente](../guia-unidad-3.md). Además: la ficha y el exportador CSV del frontend están solo en `refactor/unidad-3`; falta integrarlos en `desarrollo` |

> La misma versión debe aparecer en el tag, en el paquete y en estas notas. Hoy solo existen los tags `0.0.1` y `entrega2`, ambos sobre el prototipo v1.

---

## 5. Revisión del paquete por otro equipo

| Campo | Valor |
| --- | --- |
| Equipo revisor | Ricardo Figueroa (persona externa al proyecto) |
| Entorno limpio utilizado | Pendiente de ejecutar por Ricardo Figueroa; no se realizó en este entorno de auditoría |
| Pasos seguidos | Clonar → `cp .env.example .env` → `./scripts/setup.sh` → `npm ci && npm run dev` → ejecutar los tres casos de la sección 2 |
| Resultado | Pendiente: Ricardo Figueroa debe ejecutar el paquete siguiendo el README y registrar aquí el resultado o las correcciones aplicadas |
| Fecha | 2026-11-22 |

---

## 6. Informe breve de cierre

- **Alcance entregado:** backend v2 modular por dominios y frontend React; tres intervenciones de la Unidad 3 ([ficha](../guia-unidad-3.md)).
- **Decisiones de construcción y sus efectos:** monolito modular Django con una sola fuente por regla (`roles.py`, `locks.py`, `rules.py`); CSV como utilidad pura reutilizable; exportación de auditoría como segundo consumidor. Efecto: menos archivos a editar por cambio de regla.
- **Mejoras verificadas:** indicadores antes/después de la ficha; suite con cobertura ≥90 % en CI; contrato OpenAPI validado en cada push.
- **Pendientes priorizados:** [deuda registrada](../guia-unidad-3.md#6-deuda-pendiente), con responsable y condición de revisión.
