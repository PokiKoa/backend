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
uv run poki_koa seed_demo   # Carga datos clínicos de prueba y superusuario admin / admin2026
uv run poki_koa runserver
```

## Verificación y Pruebas

```bash
uv run ruff check src
uv run poki_koa makemigrations --check
uv run pytest
uv run poki_koa test
```

## Documentación del Proyecto

- [AGENTS.md](./AGENTS.md): Guía operativa, reglas de código y convenciones del repositorio.
- [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md): Arquitectura modular por dominios, reglas fisiológicas y ciclo de vida de alertas.
- [docs/API_REFERENCE.md](./docs/API_REFERENCE.md): Contrato REST `/api/v1/`, canales WebSocket `/ws/v1/` y formato de errores.
- [docs/SECURITY_AND_RBAC.md](./docs/SECURITY_AND_RBAC.md): Autenticación JWT, matriz de permisos RBAC, API keys por dispositivo y 2FA (TOTP).
- [docs/DATA_SCHEMA.md](./docs/DATA_SCHEMA.md): Esquema de datos relacional v2, diagrama ER e invariantes.
- [docs/DEPLOYMENT_AND_OPERATIONS.md](./docs/DEPLOYMENT_AND_OPERATIONS.md): Guía de servidor ASGI (`Uvicorn`), archivos estáticos (`WhiteNoise`), producción y operación.
