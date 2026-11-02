# Poki Koa — Backend de Monitoreo Neonatal

> **Poki** (niño/hijo) · **Koa** (alegría) — Lengua Rapa Nui

Backend REST y tiempo real para monitoreo clínico en unidades de neonatología: pacientes recién nacidos, cunas e incubadoras con telemetría e historial de signos vitales, motor de alertas clínicas, planes de cuidado, medicación con control de stock, autorización por roles y auditoría clínica.

## Stack

- **Python 3.12+** · **Django 5.2+** · **Django REST Framework**
- **PostgreSQL** (persistencia relacional) · **Django Channels + Redis** (tiempo real)
- **OpenAPI 3** (`drf-spectacular`) · **uv** · **Ruff** · **pytest**

## Inicio rápido

```bash
uv sync
uv run poki_koa migrate
uv run poki_koa
```

## Verificación

```bash
uv run ruff check src
uv run poki_koa makemigrations --check
uv run poki_koa test
```

## Documentación y Decisiones de Arquitectura

- [AGENTS.md](./AGENTS.md): Guía operativa, reglas de código y estado del proyecto.
- [docs/ADR-001.md](./docs/ADR-001.md): Extracción de dominio desde IncuNest y qué se descartó.
- [docs/ADR-002.md](./docs/ADR-002.md): Contrato `/api/v1/` y mapeo de campos respecto a la v1 (`entrega2`).
- [docs/ADR-003.md](./docs/ADR-003.md): Autenticación JWT, RBAC, API keys por dispositivo y decisión sobre 2FA (TOTP).
- [docs/DATA_SCHEMA.md](./docs/DATA_SCHEMA.md): Esquema de datos relacional v2 y diagrama ER.
