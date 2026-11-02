## 1. Qué es este proyecto

**Poki Koa** es el backend de un sistema de monitoreo neonatal para unidades de neonatología: pacientes (recién nacidos), cunas/dispositivos con telemetría de signos vitales e historial, motor de alertas clínicas, planes de cuidado, observaciones, medicación vinculada a un catálogo con stock, control de acceso por roles (RBAC) y auditoría clínica.

Este repositorio es **solo backend**. El frontend (React + Vite) vive en otro repositorio.

La evidencia académica de la versión prototipo inicial (v1) se conserva en el tag `entrega2` sobre `main`. La rama `rewrite/v2` contiene la reescritura profesional por aplicaciones de dominio.

## 2. Stack y Arquitectura (v2)

| Tema | Valor |
|---|---|
| Lenguaje | Python >= 3.12 |
| Framework | Django >= 5.2, Django REST Framework >= 3.18 |
| Tiempo real | Django Channels + Redis |
| Base de datos | PostgreSQL (Docker Compose en desarrollo / CI) |
| Autenticación | JWT (access corto + refresh con rotación y revocación) + API Key por dispositivo |
| Documentación API | OpenAPI 3 (`drf-spectacular`) bajo `/api/v1/schema/` y `/api/v1/docs/` |
| Gestor / Linter / Tests | `uv` (hatchling), `ruff`, `pytest` + `pytest-django` |
| Zona horaria / idioma | `America/Santiago`, `es-cl` (textos y errores en español; código y JSON en inglés) |

### Aplicaciones de dominio (`src/`)
- `accounts`: Usuarios (`User`), roles (`admin`, `neonatologist`, `nurse`, `pharmacist`), JWT, bloqueo temporal tras intentos fallidos y soporte 2FA (TOTP).
- `audit`: Registro inmutable de accesos y modificaciones por paciente (`AuditLog`), guardando solo nombres de campos modificados (cero datos clínicos en logs).
- `devices`: Cunas/dispositivos (`Crib`), estado operativo, asignación de paciente y autenticación de telemetría por API Key.
- `patients`: Pacientes (`Patient`) con baja lógica en egreso (`discharge`), evolución ponderal (`WeightRecord`), planes de cuidado (`CarePlan`) y observaciones (`ClinicalObservation`).
- `vitals`: Fuente única de verdad de rangos fisiológicos (`vitals/rules.py`) e histórico de lecturas por cuna y paciente (`VitalSignReading`).
- `alerts`: Umbrales configurables (`AlertThresholdConfig`), políticas de severidad (`alerts/policies.py`) y ciclo de vida de alertas (`Alert`: deduplicación, reconocimiento `acknowledge` y autorresolución).
- `medications`: Catálogo con stock (`MedicationCatalogItem`) e indicaciones por paciente (`Prescription`) con administración atómica y descuento de stock sin doble administración.

### Documentación de arquitectura (`docs/`)
- [ADR-001](docs/ADR-001.md): Qué se tomó y qué se descartó de `~/IncuNest`.
- [ADR-002](docs/ADR-002.md): Contrato `/api/v1/` y mapeo de campos de v1 a v2.
- [ADR-003](docs/ADR-003.md): Autenticación JWT, RBAC, API keys de dispositivos y decisión sobre 2FA (TOTP).
- [DATA_SCHEMA.md](docs/DATA_SCHEMA.md): Esquema de datos relacional v2, diagrama ER e invariantes.

## 3. Comandos

Ejecutar desde la raíz del repositorio:

```bash
uv sync                                  # instala dependencias desde uv.lock
uv run poki_koa migrate                  # aplica migraciones
uv run poki_koa makemigrations --check   # verifica que no falten migraciones
uv run poki_koa test                     # ejecuta la suite de pruebas actual
uv run ruff check src                    # verifica linter y estilo
```

## 4. Seguridad y datos

- Cero secretos en el repositorio: toda configuración sensible (`SECRET_KEY`, `DEBUG`, `DATABASE_URL`, `REDIS_URL`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`) proviene de variables de entorno (`settings/base.py`, `settings/dev.py`, `settings/prod.py`).
- **Usa solo datos ficticios.** Nunca cargues datos reales de pacientes ni vuelques valores clínicos en logs o registros de auditoría.
- La lógica de negocio reside en `services.py` de cada aplicación de dominio, nunca en `views.py`.

## 5. Reglas para agentes de IA

- Lee el código antes de afirmar un comportamiento; no inventes endpoints, campos ni resultados de pruebas.
- Identificadores en inglés (modelos, campos, funciones, endpoints, JSON); mensajes de error y textos al usuario en español.
- Comentarios en español, solo cuando expliquen un *porqué* no obvio (sin docstrings redundantes).
- Una sola fuente de verdad por regla de negocio (p. ej. rangos de signos vitales).
- Si una prueba falla, corrige la causa; no relajes aserciones para que pasen.
- Toda tarea debe separarse en commits pequeños y comprensibles; nunca envíes todo en un solo commit.

## 6. Estado de fases de reescritura (`rewrite/v2`)

- [x] **Fase 1:** Tag `entrega2`, rama `rewrite/v2`, ADR de IncuNest (`ADR-001` a `ADR-003`) y esquema de datos (`DATA_SCHEMA.md`).
- [ ] **Fase 2:** Cuentas, roles, autenticación JWT, bloqueo, rate limiting y auditoría (`accounts`, `audit`).
- [ ] **Fase 3:** Pacientes (alta, edición, egreso lógico), planes de cuidado, observaciones y cunas (`patients`, `devices`).
- [ ] **Fase 4:** Ingesta de telemetría con histórico y motor de alertas (`vitals`, `alerts`).
- [ ] **Fase 5:** Tiempo real por WebSocket autenticado (Django Channels + Redis).
- [ ] **Fase 6:** Catálogo de medicamentos con stock, prescripciones y administración atómica (`medications`).
- [ ] **Fase 7:** CI (GitHub Actions) y Docker (`Dockerfile`, `docker-compose.yml`).
