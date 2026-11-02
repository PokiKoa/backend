FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --locked --no-dev \
    && useradd --create-home --shell /bin/bash pokikoa \
    && chown -R pokikoa:pokikoa /app

USER pokikoa

EXPOSE 8000

CMD ["sh", "-c", "uv run poki_koa migrate --noinput && uv run poki_koa runserver 0.0.0.0:8000"]
