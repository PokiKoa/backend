#!/usr/bin/env bash
# Prepara el backend para desarrollo local: verifica requisitos, levanta PostgreSQL y Redis,
# instala dependencias, migra y carga datos ficticios. Se puede ejecutar varias veces.
#
#   ./scripts/setup.sh          # solo prepara
#   ./scripts/setup.sh --run    # prepara y deja uvicorn corriendo
set -euo pipefail

cd "$(dirname "$0")/.."

RUN=0
for arg in "$@"; do
  case "$arg" in
    --run) RUN=1 ;;
    -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
    *) echo "Opción desconocida: $arg" >&2; exit 2 ;;
  esac
done

paso() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[32m✔\033[0m %s\n' "$*"; }
falla() {
  printf '\n\033[1;31m✘ %s\033[0m\n' "$1" >&2
  shift
  for linea in "$@"; do printf '  %s\n' "$linea" >&2; done
  exit 1
}

# --- uv y Python -------------------------------------------------------------
paso "uv y Python"
command -v uv >/dev/null 2>&1 || falla "No se encontró uv." \
  "Instálalo con: curl -LsSf https://astral.sh/uv/install.sh | sh" \
  "y abre una terminal nueva."
ok "$(uv --version)"

PY_VERSION="$(tr -d '[:space:]' < .python-version 2>/dev/null || true)"
[ -n "$PY_VERSION" ] || falla ".python-version está vacío o no existe." "Debe contener la versión de Python del proyecto (por ejemplo 3.12)."
# Instala el Python del proyecto aunque el sistema traiga otro (p. ej. Fedora con 3.15)
uv python install "$PY_VERSION" >/dev/null
ok "Python $PY_VERSION disponible para uv"

# --- Docker ------------------------------------------------------------------
paso "Docker (PostgreSQL y Redis)"
command -v docker >/dev/null 2>&1 || falla "No se encontró docker." \
  "Fedora:        sudo dnf install docker-cli moby-engine docker-compose" \
  "Debian/Ubuntu: https://docs.docker.com/engine/install/" \
  "macOS/Windows: instala Docker Desktop."

DOCKER=(docker)
if ! info_err="$(docker info 2>&1 >/dev/null)"; then
  if grep -qi 'permission denied' <<<"$info_err"; then
    echo "    Tu usuario no tiene permiso sobre Docker; se usará sudo (puede pedir tu contraseña)."
    echo "    Para evitarlo: sudo usermod -aG docker \"\$USER\" y vuelve a iniciar sesión."
    DOCKER=(sudo docker)
  else
    falla "No se pudo conectar con el daemon de Docker: ${info_err%%$'\n'*}" \
      "Linux:         sudo systemctl enable --now docker" \
      "macOS/Windows: abre Docker Desktop."
  fi
fi

if "${DOCKER[@]}" compose version >/dev/null 2>&1; then
  COMPOSE=("${DOCKER[@]}" compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
  [ "${DOCKER[0]}" = sudo ] && COMPOSE=(sudo docker-compose)
else
  falla "Falta el plugin 'docker compose' (el error típico es: unknown shorthand flag: 'd' in -d)." \
    "Fedora:        sudo dnf install docker-compose" \
    "Debian/Ubuntu: sudo apt install docker-compose-plugin"
fi
ok "$("${COMPOSE[@]}" version | head -1)"

# --- .env --------------------------------------------------------------------
paso "Archivo .env"
if [ -f .env ]; then
  ok ".env ya existe (no se sobrescribe)"
else
  cp .env.example .env
  ok ".env creado desde .env.example"
fi

# --- Servicios -----------------------------------------------------------------
paso "Levantando PostgreSQL y Redis"
"${COMPOSE[@]}" up -d db redis
for i in $(seq 1 30); do
  estados="$("${COMPOSE[@]}" ps --format '{{.Service}} {{.Health}}' db redis 2>/dev/null || true)"
  if [ "$(grep -c ' healthy' <<<"$estados")" -eq 2 ]; then
    ok "db y redis saludables"
    break
  fi
  [ "$i" -eq 30 ] && falla "db o redis no quedaron saludables en 60 s." \
    "Revisa: ${COMPOSE[*]} logs db redis" \
    "¿Otro PostgreSQL/Redis ocupa los puertos 5432 o 6379? (ss -ltnp | grep -E ':5432|:6379')"
  sleep 2
done

# --- Dependencias y base de datos ----------------------------------------------
paso "Dependencias (uv sync)"
uv sync
ok "entorno virtual listo en .venv"

paso "Migraciones"
uv run poki_koa migrate --noinput

paso "Datos de demostración (seed_demo)"
uv run poki_koa seed_demo

cat <<'EOF'

✔ Backend listo.
  Usuarios: admin / admin2026 · dr.soto, matrona.diaz, qf.silva / Clinica#2026

  Servidor (HTTP + WebSockets):  uv run uvicorn poki_koa.asgi:application --app-dir src --reload
  Telemetría simulada (otra terminal): uv run poki_koa simulate_telemetry --anomaly-rate 0.2 --interval 3
EOF

if [ "$RUN" -eq 1 ]; then
  paso "Iniciando uvicorn en http://localhost:8000"
  exec uv run uvicorn poki_koa.asgi:application --app-dir src --reload
fi
