FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONPATH=/app/src

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# collectstatic usa settings.dev porque prod.py exige SECRET_KEY, DATABASE_URL y ALLOWED_HOSTS,
# que no existen al construir y no deben quedar en la imagen. El resultado es el mismo: los
# estáticos dependen solo de INSTALLED_APPS, STATIC_ROOT y STORAGES, definidos en base.py y
# compartidos por ambos (lo verifica poki_koa/test_settings_parity.py).
# --no-sync evita que uv run vuelva a instalar el grupo dev recién excluido.
RUN uv sync --locked --no-dev \
    && DJANGO_SETTINGS_MODULE=poki_koa.settings.dev uv run --no-sync poki_koa collectstatic --noinput \
    && useradd --create-home --shell /bin/bash pokikoa \
    && chown -R pokikoa:pokikoa /app

# En runtime todo proceso (uvicorn, migrate, check_offline_cribs) arranca con settings.prod;
# docker-compose.yml lo cambia a settings.dev para desarrollo. UV_NO_SYNC impide que uv run
# instale dependencias al iniciar el contenedor.
ENV DJANGO_SETTINGS_MODULE=poki_koa.settings.prod \
    UV_NO_SYNC=1

USER pokikoa

EXPOSE 8000

CMD ["sh", "-c", "uv run poki_koa migrate --noinput && uv run uvicorn poki_koa.asgi:application --host 0.0.0.0 --port 8000"]
