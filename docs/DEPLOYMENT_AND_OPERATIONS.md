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
2. **Conexiones WebSocket persistentes en tiempo real** (`/ws/v1/cribs/<id>/stream/`, `/ws/v1/patients/<id>/stream/`, `/ws/v1/monitoring/stream/`).

El punto de entrada [src/poki_koa/asgi.py](../src/poki_koa/asgi.py) utiliza un `ProtocolTypeRouter` de Django Channels que inspecciona el protocolo de cada conexión entrante y la dirige al subsistema correspondiente:

```mermaid
flowchart LR
    Client["Cliente / Monitor"] -->|Puerto 8000| Uvicorn["Servidor ASGI (Uvicorn + uvloop)"]
    Uvicorn --> Router{"ProtocolTypeRouter\n(poki_koa/asgi.py)"}
    Router -->|"scope['type'] == 'http'"| DjangoHTTP["Django ASGI Handler\n(/api/v1/, /admin/, /)"]
    Router -->|"scope['type'] == 'websocket'"| Origin["SettingsOriginValidator\n(vitals/realtime.py)"]
    Origin --> JWTMiddleware["JwtWebSocketAuthMiddleware\n(vitals/realtime.py)"]
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
| `--app-dir src` | Añade `src/` al `PYTHONPATH` para que Python encuentre el paquete `poki_koa` y las apps de dominio (en el `Dockerfile` ya está definido vía `ENV PYTHONPATH=/app/src`). |
| `--host 0.0.0.0` | Escucha en todas las interfaces de red del contenedor o máquina virtual. |
| `--port 8000` | Puerto TCP donde se sirven tanto HTTP como WebSockets. |
| `--workers N` | Levanta `N` procesos independientes (recomendado: `2 * núcleos_CPU + 1`). En la imagen Docker se fija con la variable `WEB_CONCURRENCY`, que uvicorn lee directamente. Cuando se usan múltiples workers, **es obligatorio configurar `REDIS_URL`** para que los eventos WebSocket se sincronicen entre procesos. |
| `--proxy-headers` | Activo por defecto en `uvicorn`, pero solo confía en las cabeceras `X-Forwarded-*` de las IP de `--forwarded-allow-ips` (`127.0.0.1` por defecto). La IP real del cliente para la auditoría y el límite de login la resuelve Django con `TRUSTED_PROXY_COUNT` (sección 4.1), y HTTPS se detecta con `SECURE_PROXY_SSL_HEADER`. |

---

## 3. Archivos Estáticos en Producción (`WhiteNoise` + `collectstatic`)

### 3.1 ¿Qué problema resuelve `WhiteNoise`?
Cuando `DEBUG = True` (desarrollo), Django busca y sirve automáticamente los archivos CSS/JS del panel `/admin/` y de `drf-spectacular`.
Por seguridad y rendimiento, cuando **`DEBUG = False` (producción)**, Django **desactiva por completo** la entrega de archivos estáticos. Sin una capa que los sirva, al entrar a `/admin/` se vería HTML plano sin estilos.

### 3.2 Cómo funciona en Poki Koa
1. **`collectstatic`:** El comando `uv run poki_koa collectstatic --noinput` recolecta los archivos CSS/JS de todos los paquetes instalados y los copia en la carpeta `staticfiles/` (`STATIC_ROOT`).
2. **En la imagen Docker:** `collectstatic` se ejecuta al construir con `settings.dev`, porque `prod.py` exige `SECRET_KEY`, `DATABASE_URL` y `ALLOWED_HOSTS`, que no existen en el build ni deben quedar en la imagen. El resultado es idéntico: los estáticos dependen solo de `INSTALLED_APPS`, `STATIC_ROOT` y `STORAGES`, definidos en `base.py`. [src/poki_koa/test_settings_parity.py](../src/poki_koa/test_settings_parity.py) lo verifica. En runtime la imagen fija `DJANGO_SETTINGS_MODULE=poki_koa.settings.prod`.
3. **`WhiteNoiseMiddleware`:** Configurado en [src/poki_koa/settings/base.py](../src/poki_koa/settings/base.py) justo debajo de `SecurityMiddleware`, intercepta cualquier petición a `/static/...` y sirve los archivos directamente desde memoria con compresión **Gzip** (`CompressedStaticFilesStorage`; Brotli solo si se instala el paquete `brotli`) y cabeceras `Cache-Control` óptimas, sin necesidad de instalar ni mantener un servidor Nginx aparte solo para archivos estáticos.

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
| `ALLOWED_HOSTS` | `pokikoa.example.org` | Lista de dominios autorizados en la cabecera HTTP `Host` (y orígenes WebSocket del mismo sitio). |
| `CORS_ALLOWED_ORIGINS` | `https://pokikoa.example.org` | Orígenes de frontend React autorizados a consumir la API y abrir WebSockets. |

Variables opcionales relevantes en producción:

| Variable | Por defecto | Función |
|---|---|---|
| `CSRF_TRUSTED_ORIGINS` | `CORS_ALLOWED_ORIGINS` | Orígenes aceptados en formularios con CSRF (admin de Django detrás de HTTPS). |
| `TRUSTED_PROXY_COUNT` | `0` | Proxies inversos propios delante de la API. Con `1` (Caddy), la IP del cliente es la última entrada de `X-Forwarded-For`; con `0` se ignora la cabecera. La usan la auditoría y el límite de login (`NUM_PROXIES` de DRF). |
| `REFRESH_COOKIE_NAME`, `REFRESH_COOKIE_SAMESITE`, `REFRESH_COOKIE_DOMAIN` | `poki_refresh`, `Lax`, vacío | Cookie httpOnly del refresh token. En `prod.py` siempre es `Secure`. |
| `LOG_LEVEL` | `INFO` | Nivel de los logs de consola. |
| `SEED_DEMO_PASSWORD` | vacío | Contraseña de los usuarios de `seed_demo`. Con `DEBUG=False` es obligatoria para ejecutar el comando. Si está definida, también rota la clave de los usuarios de demostración que ya existen; sin ella, sus claves no se tocan. |

### 4.2 Persistencia de conexiones a PostgreSQL (`CONN_MAX_AGE`)
En [src/poki_koa/settings/prod.py](../src/poki_koa/settings/prod.py), la base de datos define:
- `CONN_MAX_AGE = 60` (reutiliza conexiones TCP hacia PostgreSQL durante 60 segundos en lugar de abrir y cerrar una conexión nueva en cada petición HTTP o ingesta de telemetría).
- `CONN_HEALTH_CHECKS = True` (verifica que la conexión del pool siga viva antes de iniciar una transacción).

### 4.3 Seguridad HTTP y TLS
- `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`: Detecta HTTPS cuando el contenedor corre detrás de un proxy inverso o balanceador TLS.
- `SECURE_SSL_REDIRECT = True`: Redirige tráfico HTTP a HTTPS (puede desactivarse en pruebas locales de contenedor con `SECURE_SSL_REDIRECT=False`). `SECURE_REDIRECT_EXEMPT` excluye solo `/api/v1/health/ready/`, al que el healthcheck del contenedor llama por HTTP sin pasar por el proxy.
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
   - `uv run poki_koa check_offline_cribs --every 60` corre como proceso continuo y repite la verificación cada 60 segundos; un error transitorio de base de datos se informa sin detener el monitor. En `docker-compose.yml` lo ejecuta el servicio `offline-monitor`, que comparte la imagen y el entorno de `app`.
   - Como corre en otro proceso, sus alertas solo llegan a los WebSockets si `REDIS_URL` está configurada (en Docker Compose ya lo está). Sin `--every`, el comando hace una sola verificación y sirve para un `cron` del sistema.

---

## 6. Despliegue de producción con Docker Compose (`docker-compose.prod.yml`)

Cada centro despliega su propia instancia en su propio dominio; los ejemplos usan `pokikoa.example.org`. El frontend y la API van en el **mismo dominio**: así la cookie de refresh (`SameSite=Lax`) viaja sin CORS y los WebSockets usan el mismo origen.

```mermaid
flowchart LR
    Browser["Navegador"] -->|"HTTPS :443"| Proxy["Proxy TLS del host (Caddy)"]
    Proxy -->|"/api/* /ws/* /admin/* /static/*"| App["app :8000\n(127.0.0.1 del host)"]
    Proxy -->|"resto de rutas"| Web["Frontend estático (imagen del repo frontend)"]
    App --> DB[("db: PostgreSQL 16\nsin puertos publicados")]
    App --> Redis[("redis: capa de canales\nsin puertos publicados")]
    Monitor["offline-monitor"] --> DB
    Monitor --> Redis
```

### 6.1 Servicios

| Servicio | Imagen | Función |
|---|---|---|
| `db` | `postgres:16-alpine` | Base de datos en el volumen `postgres_data`. Sin puertos hacia el host. |
| `redis` | `redis:7-alpine` | Capa de canales de WebSockets, sin persistencia en disco. Sin puertos hacia el host. |
| `app` | `poki-koa-backend:prod` | Aplica migraciones y levanta uvicorn (HTTP + WebSockets). Publica solo en `127.0.0.1:${APP_HOST_PORT:-8000}`. Su healthcheck llama a `/api/v1/health/ready/`. |
| `offline-monitor` | `poki-koa-backend:prod` | `check_offline_cribs --every 60`: marca cunas sin telemetría y emite alertas `sensor_fault`. Arranca cuando `app` está sana (migraciones aplicadas). |

Todos usan `restart: unless-stopped` y `DJANGO_SETTINGS_MODULE=poki_koa.settings.prod` con `DEBUG=False` fijo.

### 6.2 Preparar la configuración

```bash
cp .env.prod.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(50))"   # pegar en SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # pegar en POSTGRES_PASSWORD
chmod 600 .env
```

`SECRET_KEY`, `POSTGRES_PASSWORD`, `ALLOWED_HOSTS` y `CORS_ALLOWED_ORIGINS` son obligatorias: compose se detiene antes de crear contenedores si falta alguna (`${VAR:?mensaje}`). El primer valor de `ALLOWED_HOSTS` debe ser un nombre concreto (`pokikoa.example.org`), porque el healthcheck lo envía como `Host`. `.env` nunca se versiona.

### 6.3 Construir y levantar

```bash
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d --wait
docker compose -f docker-compose.prod.yml ps     # app debe quedar (healthy)
```

Si la imagen se construye en otra máquina, se puede trasladar con `docker save poki-koa-backend:prod | gzip > backend.tar.gz` y `docker load < backend.tar.gz`, y luego levantar con `up -d --no-build`.

### 6.4 Qué espera la API del proxy TLS

El proxy del host (fuera de este repositorio) debe:

- Reenviar `/api/*`, `/ws/*`, `/admin/*` y `/static/*` a `127.0.0.1:8000`, con soporte de WebSocket (Caddy lo hace por defecto con `reverse_proxy`).
- Conservar el `Host` original (el dominio del centro) y enviar `X-Forwarded-Proto: https`. Sin esa cabecera, Django redirige a HTTPS en bucle.
- Agregar la IP del cliente en `X-Forwarded-For`, como hace Caddy. Con un solo proxy, `TRUSTED_PROXY_COUNT=1`.

### 6.5 Primer usuario

```bash
docker compose -f docker-compose.prod.yml exec app uv run poki_koa createsuperuser
```

Para cargar los datos ficticios de demostración, `seed_demo` exige una contraseña robusta propia (las de desarrollo `admin2026` / `Clinica#2026` se rechazan):

```bash
docker compose -f docker-compose.prod.yml exec -e SEED_DEMO_PASSWORD='<contraseña robusta>' app uv run poki_koa seed_demo
```

### 6.6 Verificación y operación

```bash
curl -s -H 'Host: pokikoa.example.org' http://127.0.0.1:8000/api/v1/health/ready/   # {"status": "ok"}
curl -s https://pokikoa.example.org/api/v1/health/ready/                              # a través del proxy
docker compose -f docker-compose.prod.yml logs -f app offline-monitor
```

- **Actualizar:** `git pull` (o cargar la nueva imagen), `docker compose -f docker-compose.prod.yml up -d --build --wait`. Las migraciones se aplican al iniciar `app`.
- **Respaldo:** `docker compose -f docker-compose.prod.yml exec -T db pg_dump -U poki_koa -Fc poki_koa > poki_koa-$(date +%F).dump`.
- **Restaurar:** `docker compose -f docker-compose.prod.yml exec -T db pg_restore -U poki_koa -d poki_koa --clean --if-exists < archivo.dump`.
