# Integración Continua (CI) — Hito 2

El flujo de integración continua está configurado en [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) y se ejecuta en GitHub Actions cada vez que se hace `push` o `pull_request` a `main` o `desarrollo`.

## Pasos que ejecuta el workflow

1. **Instalación del entorno (`uv sync --locked`):** instala las dependencias exactas definidas en `uv.lock`.
2. **Revisión de código (`uv run ruff check src test`):** revisa errores de sintaxis, imports sin usar y reglas de estilo.
3. **Chequeo de migraciones (`uv run poki_koa makemigrations --check --dry-run`):** verifica que no haya cambios en `models.py` sin su migración creada.
4. **Pruebas y cobertura (`coverage run` + `coverage report -m --fail-under=85`):** corre las 57 pruebas de Django y las 14 pruebas unitarias de `test/`. Si alguna prueba falla o la cobertura total baja de 85%, el workflow falla.
5. **Reporte descargable:** sube el reporte HTML y XML como artefacto (`reporte-cobertura-hito2`) en la ejecución de GitHub Actions.
