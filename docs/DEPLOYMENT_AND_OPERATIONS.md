# Guía de Despliegue, Servidor ASGI (`Uvicorn`) y Operación — Poki Koa

Este documento explica en detalle cómo se ejecuta **Poki Koa** en entornos de desarrollo y producción, por qué utiliza un servidor **ASGI (`Uvicorn`)** en lugar de un servidor WSGI tradicional, cómo se sirven los archivos estáticos mediante **`WhiteNoise`** y qué considerar al escalar el sistema a futuro.

---

## 1. ¿Por qué `Uvicorn` (ASGI) en lugar de `runserver` o `Gunicorn` (WSGI)?

### 1.1 Diferencia entre WSGI y ASGI
En el ecosistema Python/Django existen dos estándares para comunicar el servidor web con la aplicación:

| Característica | **WSGI** (*Web Server Gateway Interface*) | **ASGI** (*Asynchronous Server Gateway Interface*) |
|---|---|---|
| Modelo de ejecución | Síncrono (petición → respuesta corta) | Asíncrono y orientado a eventos |
| Protocolos soportados | Solo HTTP/1.1 | **HTTP/1.1, HTTP/2 y WebSockets (`ws://` / `wss://`)** |
| Conexiones persistentes | Bloquea un hilo/proceso por conexión | Maneja miles de conexiones abiertas en un mismo bucle de eventos (`uvloop`) |
| Ejemplos de servidores | `gunicorn` (modo clásico), `uwsgi` | **`uvicorn`**, `daphne`, `hypercorn` |

### 1.2 Cómo enruta el tráfico `poki_koa/asgi.py`
**Poki Koa** necesita atender simultáneamente dos tipos de tráfico en el mismo puerto (`8000`):
1. **Peticiones HTTP REST y vistas HTML** (`/api/v1/...`, `/admin/`, `/`).
2. **Conexiones WebSocket persistentes en tiempo real** (`/ws/v1/cribs/<id>/`, `/ws/v1/patients/<id>/`, `/ws/v1/alerts/`).

El punto de entrada [src/poki_koa/asgi.py](../src/poki_koa/asgi.py) utiliza un `ProtocolTypeRouter` de Django Channels que inspecciona el protocolo de cada conexión entrante y la dirige al subsistema correspondiente:

```mermaid
flowchart LR
    Client["Cliente / Monitor"] -->|Puerto 8000| Uvicorn["Servidor ASGI (Uvicorn + uvloop)"]
    Uvicorn --> Router{"ProtocolTypeRouter\n(poki_koa/asgi.py)"}
    Router -->|"scope['type'] == 'http'"| DjangoHTTP["Django ASGI Handler\n(/api/v1/, /admin/, /)"]
    Router -->|"scope['type'] == 'websocket'"| JWTMiddleware["JWTWebSocketAuthMiddleware\n(vitals/consumers.py)"]
    JWTMiddleware <--> Redis[("Redis Channel Layer\n(Pub/Sub en tiempo real)")]
```

> [!WARNING]
> **Por qué no usar `manage.py runserver` en producción:**
> `runserver` está diseñado exclusivamente para desarrollo local: no aplica límites de concurrencia, recarga módulos en memoria y no está endurecido frente a ataques de agotamiento de sockets (Slowloris). En producción (y en `Dockerfile`), siempre debe utilizarse **`uvicorn`**.

---

## 2. Cómo usar `Uvicorn` en Desarrollo y Producción

### 2.1 En desarrollo local (con recarga automática)
Puedes usar tanto `uv run poki_koa runserver` como `uvicorn` directamente. Para probar el servidor ASGI real con recarga en caliente (`--reload`). `asgi.py` lee el archivo `.env` antes de elegir los settings, así que basta con `cp .env.example .env` (que fija `DJANGO_SETTINGS_MODULE=poki_koa.settings.dev`); sin él se cargan los settings de producción:

```bash
uv run uvicorn poki_koa.asgi:application --app-dir src --host 127.0.0.1 --port 8000 --reload
```

### 2.2 En producción / Docker
En contenedores o servidores Linux productivos se ejecuta sin `--reload` y escuchando en `0.0.0.0`:

```bash
# 1. Aplicar migraciones pendientes
uv run poki_koa migrate --noinput

# 2. Empaquetar archivos estáticos (si no se hizo en el build de la imagen)
uv run poki_koa collectstatic --noinput

# 3. Iniciar servidor ASGI Uvicorn
uv run uvicorn poki_koa.asgi:application --app-dir src --host 0.0.0.0 --port 8000 --workers 2 --proxy-headers
```

### 2.3 Significado de cada argumento de `uvicorn`

| Flag | Propósito |
|---|---|
| `poki_koa.asgi:application` | Ruta al módulo Python (`poki_koa/asgi.py`) y al objeto `application` que expone el `ProtocolTypeRouter`. |
| `--app-dir src` | Añade `src/` al `PYTHONPATH` para que Python encuentre el paquete `poki_koa` y las 7 apps de dominio (en el `Dockerfile` ya está definido vía `ENV PYTHONPATH=/app/src`). |
| `--host 0.0.0.0` | Escucha en todas las interfaces de red del contenedor o máquina virtual. |
| `--port 8000` | Puerto TCP donde se sirven tanto HTTP como WebSockets. |
| `--workers N` | Levanta `N` procesos independientes (recomendado: `2 * núcleos_CPU + 1`). Cuando se usan múltiples workers, **es obligatorio configurar `REDIS_URL`** para que los eventos WebSocket se sincronicen entre procesos. |
| `--proxy-headers` | Permite que `uvicorn` confíe en cabeceras `X-Forwarded-For` y `X-Forwarded-Proto` enviadas por un balanceador o proxy inverso (Nginx, Caddy, Cloudflare, AWS ALB). |

---

## 3. Archivos Estáticos en Producción (`WhiteNoise` + `collectstatic`)

### 3.1 ¿Qué problema resuelve `WhiteNoise`?
Cuando `DEBUG = True` (desarrollo), Django busca y sirve automáticamente los archivos CSS/JS del panel `/admin/` y de `drf-spectacular`.
Por seguridad y rendimiento, cuando **`DEBUG = False` (producción)**, Django **desactiva por completo** la entrega de archivos estáticos. Sin una capa que los sirva, al entrar a `/admin/` se vería HTML plano sin estilos.

### 3.2 Cómo funciona en Poki Koa
1. **`collectstatic`:** El comando `uv run poki_koa collectstatic --noinput` recolecta los archivos CSS/JS de todos los paquetes instalados y los copia en la carpeta `staticfiles/` (`STATIC_ROOT`).
2. **`WhiteNoiseMiddleware`:** Configurado en [src/poki_koa/settings/base.py](../src/poki_koa/settings/base.py) justo debajo de `SecurityMiddleware`, intercepta cualquier petición a `/static/...` y sirve los archivos directamente desde memoria con compresión **Gzip / Brotli** (`CompressedStaticFilesStorage`) y cabeceras `Cache-Control` óptimas, sin necesidad de instalar ni mantener un servidor Nginx aparte solo para archivos estáticos.

---

## 4. Configuración de Producción (`settings/prod.py`)

Para ejecutar el sistema en modo productivo se define `DJANGO_SETTINGS_MODULE=poki_koa.settings.prod`. Este módulo activa automáticamente:

### 4.1 Variables de entorno obligatorias en `prod.py`
| Variable | Ejemplo | Función |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `poki_koa.settings.prod` | Carga la configuración endurecida de producción. |
| `SECRET_KEY` | Cadena aleatoria de 50+ caracteres | Firma criptográfica de tokens JWT y sesiones. |
| `DEBUG` | `False` | Desactiva trazas de depuración públicas. |
| `DATABASE_URL` | `postgres://user:pass@host:5432/poki_koa` | Conexión obligatoria a PostgreSQL 16 (sin fallback a SQLite). |
| `REDIS_URL` | `redis://redis:6379/0` | Canal distribuido para WebSockets entre workers `uvicorn`. |
| `ALLOWED_HOSTS` | `api.pokikoa.cl,localhost` | Lista de dominios autorizados en la cabecera HTTP `Host`. |
| `CORS_ALLOWED_ORIGINS` | `https://app.pokikoa.cl` | Orígenes de frontend React autorizados a consumir la API. |

### 4.2 Persistencia de conexiones a PostgreSQL (`CONN_MAX_AGE`)
En [src/poki_koa/settings/prod.py](../src/poki_koa/settings/prod.py), la base de datos define:
- `CONN_MAX_AGE = 60` (reutiliza conexiones TCP hacia PostgreSQL durante 60 segundos en lugar de abrir y cerrar una conexión nueva en cada petición HTTP o ingesta de telemetría).
- `CONN_HEALTH_CHECKS = True` (verifica que la conexión del pool siga viva antes de iniciar una transacción).

### 4.3 Seguridad HTTP y TLS
- `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`: Detecta HTTPS cuando el contenedor corre detrás de un proxy inverso o balanceador TLS.
- `SECURE_SSL_REDIRECT = True`: Redirige tráfico HTTP a HTTPS (puede desactivarse en pruebas locales de contenedor con `SECURE_SSL_REDIRECT=False`).
- `SESSION_COOKIE_SECURE = True` y `CSRF_COOKIE_SECURE = True`: Las cookies nunca viajan por canales no cifrados.
- `SECURE_HSTS_SECONDS = 31536000`: Activa *HTTP Strict Transport Security* por 1 año.
- `X_FRAME_OPTIONS = "DENY"` y `SECURE_CONTENT_TYPE_NOSNIFF = True`: Mitiga clickjacking y ataques de *MIME sniffing*.

---

## 5. Consideraciones a Futuro (Escalamiento y Operación)

1. **Múltiples réplicas o workers de `Uvicorn`:**
   - Si no se define `REDIS_URL`, Django Channels usa `InMemoryChannelLayer`, el cual solo funciona dentro de un único proceso.
   - Al escalar a `--workers 2` o más contenedores, asegúrate siempre de que `REDIS_URL` apunte a una instancia Redis compartida (`redis:7-alpine`). Puedes verificar qué backend está activo visitando `GET /api/v1/health/`.
2. **Particionamiento / Retención de `VitalSignReading`:**
   - Si una unidad de 20 cunas envía telemetría cada 5 segundos, se generan ~345.000 lecturas por día. Los índices compuestos `(patient_id, -recorded_at)` y `(crib_id, -recorded_at)` mantienen las consultas rápidas, y a futuro en PostgreSQL se puede activar particionamiento mensual por rango sobre `recorded_at` o la extensión `TimescaleDB` sin cambiar el código de Django.
3. **Detección periódica de cunas desconectadas (`OFFLINE`):**
   - El comando `uv run poki_koa check_offline_cribs` (implementado en la Fase 2) puede programarse mediante un `cron` del sistema o un servicio ligero en `docker-compose.yml` cada 60 segundos para vigilar cunas que dejen de emitir señal.
