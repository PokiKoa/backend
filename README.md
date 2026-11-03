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

Levanta PostgreSQL, Redis, la API en `http://localhost:8000` y el servicio `offline-monitor`, que cada 60 segundos marca como `offline` las cunas sin telemetría reciente y emite alertas `sensor_fault`.

## Ejecución local con `uv`

La forma más simple es el script de instalación. Verifica los requisitos (uv, Python del proyecto, Docker y el plugin `compose`), crea `.env` si falta, levanta PostgreSQL y Redis, y ejecuta `uv sync`, `migrate` y `seed_demo`. Si algo falta, se detiene y dice cómo corregirlo. Se puede ejecutar varias veces:

```bash
./scripts/setup.sh          # prepara todo
./scripts/setup.sh --run    # prepara y deja uvicorn corriendo
```

Pasos equivalentes a mano:

```bash
cp .env.example .env          # fija DJANGO_SETTINGS_MODULE=poki_koa.settings.dev
docker compose up -d db redis # PostgreSQL y Redis locales
uv sync
uv run poki_koa migrate
uv run poki_koa seed_demo     # Carga datos clínicos de prueba y superusuario admin / admin2026
uv run uvicorn poki_koa.asgi:application --app-dir src --reload  # HTTP + WebSockets
```

Para desarrollar el frontend con datos en vivo, con el servidor ya levantado y en otra terminal:

```bash
uv run poki_koa simulate_telemetry               # lecturas cada 5 s en las cunas ocupadas
uv run poki_koa simulate_telemetry --anomaly-rate 0.3 --interval 2  # más episodios y alertas
```

El simulador rota la API Key de cada cuna simulada (por eso solo corre con `DEBUG=True`) y envía las lecturas por HTTP, de modo que los WebSockets las reciben sin necesidad de Redis. Genera episodios de bradicardia, taquicardia, desaturación, hipo/hipertermia y desconexión de cánula que luego se recuperan, ejercitando la creación y la autorresolución de alertas.

### Problemas comunes

| Síntoma | Causa y solución |
| --- | --- |
| `unknown shorthand flag: 'd' in -d` | Falta el plugin `docker compose`. Fedora: `sudo dnf install docker-compose`; Debian/Ubuntu: `sudo apt install docker-compose-plugin`. |
| `failed to connect to the docker API ... no such file` | El daemon está apagado: `sudo systemctl enable --now docker`. |
| `permission denied ... docker.sock` | `sudo usermod -aG docker "$USER"` y vuelve a iniciar sesión (o usa `sudo docker compose`). |
| `No interpreter found for Python 3.12` | `uv python install 3.12` (uv usa la versión de `.python-version`, no la del sistema). |
| `ImportError: no pq wrapper available` | Entorno creado con otro Python o dependencias antiguas: `rm -rf .venv && uv sync`. |

Sin `.env` ni `DJANGO_SETTINGS_MODULE` exportada, `asgi.py` y `wsgi.py` cargan `settings.prod` y fallan si falta `SECRET_KEY`: es intencional para que un despliegue mal configurado nunca arranque con `DEBUG`. `uv run poki_koa runserver` no sirve WebSockets.

## Verificación y Pruebas

```bash
uv run ruff check src
uv run poki_koa makemigrations --check
uv run pytest
uv run poki_koa test
```

## Desarrollo junto al frontend

El frontend (React + Vite) vive en [PokiKoa/frontend](https://github.com/PokiKoa/frontend), rama `rewrite/v2`. Clónalo junto a este repositorio (`../frontend`) y sigue su README: levanta este backend con `uvicorn`, opcionalmente `simulate_telemetry`, y luego `npm run dev`. Vite redirige `/api` y `/ws` a `http://localhost:8000`, así la cookie httpOnly del refresh funciona sin CORS. Usuarios de demo de `seed_demo`: `admin` / `admin2026`, y `dr.soto`, `matrona.diaz` y `qf.silva` con `Clinica#2026`.

## Contrato OpenAPI para el frontend

`openapi/schema.yml` es el contrato versionado de la API; CI verifica que coincida con el código. El frontend puede generar sus tipos TypeScript desde ese archivo sin autenticarse contra el backend (`/api/v1/schema/` exige sesión):

```bash
npx openapi-typescript ../backend/openapi/schema.yml -o src/api/schema.d.ts
```

Tras cambiar la API, regenera el archivo:

```bash
uv run poki_koa spectacular --validate --fail-on-warn --file openapi/schema.yml
```

## Documentación del Proyecto

- [AGENTS.md](./AGENTS.md): Guía operativa, reglas de código y convenciones del repositorio.
- [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md): Arquitectura modular por dominios, reglas fisiológicas y ciclo de vida de alertas.
- [docs/API_REFERENCE.md](./docs/API_REFERENCE.md): Contrato REST `/api/v1/`, canales WebSocket `/ws/v1/` y formato de errores.
- [docs/SECURITY_AND_RBAC.md](./docs/SECURITY_AND_RBAC.md): Autenticación JWT, matriz de permisos RBAC, API keys por dispositivo y 2FA (TOTP).
- [docs/DATA_SCHEMA.md](./docs/DATA_SCHEMA.md): Esquema de datos relacional v2, diagrama ER e invariantes.
- [docs/DEPLOYMENT_AND_OPERATIONS.md](./docs/DEPLOYMENT_AND_OPERATIONS.md): Guía de servidor ASGI (`Uvicorn`), archivos estáticos (`WhiteNoise`), producción y operación.
