# 05 · Entrega: versión, paquete, calidad y revisión

## 1. Versión

| Repositorio | Tag | Dónde coincide la versión |
|---|---|---|
| backend | **`2.1.0`** | `pyproject.toml`, `uv.lock`, tag, GitHub Release y estas notas |
| frontend | **`2.1.0`** | `package.json`, `package-lock.json`, tag, GitHub Release y sus notas |

**Por qué 2.1.0 (SemVer):** el contrato REST `/api/v1/` de la `2.0.0` no cambia de forma incompatible (nuevos módulos internos, documentación, empaquetado y una corrección de un código de error 404). Es un cambio *menor y compatible*. La `2.0.0` previa (`cd492fe`) no se movió porque ya estaba publicada; la `0.0.1` y `entrega2` son del prototipo v1 incompatible.

El commit exacto de cada tag figura en la página de la Release correspondiente.

## 2. Notas de versión 2.1.0 (2026-11-23)

**Cambios**
- Intervenciones de la Unidad 3: guarda de rol central, validaciones y bloqueo compartidos, exportador CSV reutilizable (frontend).
- Corrección: un recurso inexistente responde `code: "not_found"` (antes `api_error`; el status 404 no cambia).
- Frontend: tipos de la API regenerados desde el contrato actual del backend.
- Documentación de cierre en `hito3/` y `THIRD_PARTY_LICENSES.md` en ambos repos.

**Actualizar desde 2.0.0**
```bash
git fetch --tags && git checkout 2.1.0
uv sync --locked && uv run poki_koa migrate     # backend (sin migraciones nuevas)
npm ci && npm run build                          # frontend
```

**Limitaciones conocidas:** ver [01 §6](01-diagnostico-e-intervenciones.md) (Redis caído sin `try/except`, export de auditoría limitado a 100 filas, páginas con carga manual).

## 3. Calidad automática (ejecutado el 2026-11-23)

| Repo | Linter y formato | Pruebas | Cobertura | Build |
|---|---|---|---|---|
| backend | `ruff check` y `ruff format --check`: sin hallazgos; `makemigrations --check` limpio | **217 pasan** (PostgreSQL 16 y Redis 7 reales) | **95,2 %** líneas y ramas (`src/`, umbral 90 %) | Esquema OpenAPI idéntico a `openapi/schema.yml` |
| frontend | `oxlint` y `prettier --check`: sin hallazgos | **129 pasan**, 4 omitidas (e2e) | 71 % de líneas | `tsc -b && vite build`: correcto |

**Reportes y CI**
- Cobertura backend: artefacto `cobertura-backend` de cada run de Actions (HTML y XML).
- CI backend: [ejecuciones en `main`](https://github.com/PokiKoa/backend/actions?query=branch%3Amain) · CI frontend: [ejecuciones en `main`](https://github.com/PokiKoa/frontend/actions?query=branch%3Amain). El run de la PR de cierre aparece en la propia PR (pestaña *Checks*).

## 4. Paquete

| Qué | Contenido |
|---|---|
| **GitHub Release `2.1.0`** de cada repo | ZIP del código (`git archive`) con `.env.example`, `.env.prod.example`, `uv.lock`/`package-lock.json`, `docker-compose.prod.yml` (backend), `seed_demo` (datos ficticios) y `THIRD_PARTY_LICENSES.md` |
| Cómo instalarlo | README de la raíz → «Ejecución con Docker Compose» (o `./scripts/setup.sh`) |
| Despliegue de producción | [`docs/info_despliegue.md`](../docs/info_despliegue.md) |
| Licencias | [`THIRD_PARTY_LICENSES.md`](../THIRD_PARTY_LICENSES.md) (nota sobre `psycopg`, LGPL-3.0) |

## 5. Revisión por otro equipo — **PENDIENTE**

La guía exige que una persona de **otro equipo** pruebe el paquete en un entorno limpio. Eso no se puede hacer ni simular desde el repositorio; se deja lista la plantilla:

| Campo | A completar por quien revisa |
|---|---|
| Revisor/a y equipo | |
| Fecha y entorno limpio (SO, Docker, versión de Python/Node) | |
| Pasos | `git clone` → `cp .env.example .env` → `./scripts/setup.sh` → `npm ci && npm run dev` → caso 1, 2 y 3 de [04](04-integracion.md) |
| Resultado | |
| Correcciones al README tras la revisión | |

Quien la ejecute debe anotar aquí el resultado y corregir el README si falta algún paso.
