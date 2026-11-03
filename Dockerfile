FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONPATH=/app/src

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --locked --no-dev \
    && DJANGO_SETTINGS_MODULE=poki_koa.settings.dev uv run poki_koa collectstatic --noinput \
    && useradd --create-home --shell /bin/bash pokikoa \
    && chown -R pokikoa:pokikoa /app

USER pokikoa

EXPOSE 8000

CMD ["sh", "-c", "uv run poki_koa migrate --noinput && uv run uvicorn poki_koa.asgi:application --host 0.0.0.0 --port 8000"]
