# Poki Koa — Backend de Monitoreo Neonatal

> **Poki** (niño/hijo) · **Koa** (alegría) — Lengua Rapa Nui

Backend REST (`/api/v1/`) y tiempo real (`ws/v1/`) para monitoreo clínico en unidades de neonatología: pacientes recién nacidos con baja lógica en egreso, cunas/dispositivos con telemetría por API Key e historial de signos vitales, motor de alertas con umbrales configurables, evolución ponderal, planes de cuidado, observaciones clínicas, catálogo de medicamentos con stock y administración atómica, control de acceso por roles (RBAC) y auditoría clínica sin exposición de PHI.

## Stack

- **Python 3.12+** · **Django 5.2+** · **Django REST Framework**
- **PostgreSQL 16** (persistencia relacional) · **Django Channels + Redis 7** (tiempo real WebSocket)
- **JWT + API Key de dispositivo + 2FA TOTP** · **OpenAPI 3** (`drf-spectacular`)
- **uv** · **Ruff** · **pytest** + **pytest-django**

## Ejecución con Docker Compose (recomendado)

```bash
cp .env.example .env
docker compose up --build
```

## Ejecución local con `uv`

```bash
uv sync
uv run poki_koa migrate
uv run poki_koa runserver
```

## Verificación y Pruebas

```bash
uv run ruff check src
uv run poki_koa makemigrations --check
uv run pytest
uv run poki_koa test
```

## Documentación y Decisiones de Arquitectura

- [AGENTS.md](./AGENTS.md): Guía operativa, reglas de código y estado del proyecto.
- [docs/ADR-001.md](./docs/ADR-001.md): Extracción de dominio desde IncuNest y qué se descartó.
- [docs/ADR-002.md](./docs/ADR-002.md): Contrato `/api/v1/` y mapeo de campos respecto a la v1 (`entrega2`).
- [docs/ADR-003.md](./docs/ADR-003.md): Autenticación JWT, RBAC, API keys por dispositivo y decisión sobre 2FA (TOTP).
- [docs/DATA_SCHEMA.md](./docs/DATA_SCHEMA.md): Esquema de datos relacional v2 y diagrama ER.
