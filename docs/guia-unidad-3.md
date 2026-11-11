# Guía Unidad 3: refactorización, modularización y reutilización

Ficha de evidencias para la Sumativa 3 (ISF224). Cubre los dos repositorios de la solución:

- Backend: [poki-koa-backend](https://github.com/Asulx/poki-koa-backend), rama `refactor/unidad-3`.
- Frontend: repositorio `frontend`, rama `refactor/unidad-3`, con su ficha en `docs/guia-unidad-3.md`.

> Estado: **intervenciones implementadas (2026-11-11)**. Faltan el registro del revisor, los responsables, los enlaces a los PR y la ejecución de CI.

## 0. Preparación y línea base

| Repositorio | Comando | Resultado antes de editar |
|---|---|---|
| Backend | `uv run python -m pytest` | 160 pruebas aprobadas (47 subtests) |
| Backend | `uv run ruff check src` | sin hallazgos |
| Frontend | `npm run test` | 102 pruebas aprobadas, 4 omitidas (e2e) |
| Frontend | `npm run lint` | sin hallazgos |

Revisión del comportamiento actual por un integrante distinto del autor:

| Operación revisada | Revisor | Comportamiento observado | Fecha |
|---|---|---|---|
| Egreso de paciente por una matrona (`POST /patients/<id>/discharge/`) | _(integrante distinto del autor)_ | _Registrar: 403 con el mensaje de la guarda_ | |

## 1. Intervenciones

| # | Problema o necesidad | Ubicación | Prioridad | Solución | Responsable | Commits |
|---|---|---|---|---|---|---|
| 1 | Regla de permisos por rol duplicada (24 copias de `if actor.role not in {...}: raise PermissionDomainError`) | `src/{patients,alerts,medications,devices,accounts}/services.py` y `accounts/permissions.py` | Alta | Módulo `accounts/roles.py` con conjuntos de roles y `require_role` | _(integrante)_ | `2381602` (test), `59374af` (feat), `c06c1c5`…`92ade98` (refactor por app), `380191e` |
| 2 | Validaciones duplicadas en el catálogo y bloqueo de paciente activo repetido | `src/medications/services.py`, `src/patients/services.py`, `src/alerts/services.py` | Media | Funciones `parse_*` del catálogo y módulo `patients/locks.py` con `lock_active_patient` | _(integrante)_ | ver detalle |
| 3 | El servicio de reportes mezclaba HTTP, generación CSV y descarga, y la bitácora de auditoría no podía exportarse | Frontend: `src/services/reportesService.ts`, `src/pages/registros/RegistrosPage.tsx` | Media | Exportador reutilizable `src/utils/csv.ts` (`toCsv`, `downloadCsv`) con dos consumidores reales | _(integrante)_ | Frontend `00ff6ac`…`5c2e8bd`, ver `frontend/docs/guia-unidad-3.md` |

### Intervención 1: guarda de rol centralizada

- **Consecuencia del problema:** cambiar quién puede ejecutar una operación obligaba a editar varios archivos; los conjuntos de roles se escribían a mano en cada servicio y en los permisos DRF, y podían divergir.
- **Protección previa:** `src/accounts/test_role_guards.py` fija, para las 24 operaciones protegidas, los roles admitidos y el mensaje exacto de rechazo de cada rol no admitido. Se escribió y aprobó antes de tocar los servicios.
- **Pasos:** un commit por transformación: crear el módulo con su contrato, reemplazar la guarda app por app (suite completa tras cada una) y hacer que los permisos DRF usen las mismas constantes.

| Indicador | Antes | Después |
|---|---|---|
| Definiciones inline de la regla "rol permitido" | 24 en servicios + 5 en `permissions.py` | 1 (`accounts.roles.require_role` / `has_role`) |
| Lugares a editar para cambiar el conjunto "personal clínico" | 10 (9 guardas + `IsClinicalStaff`) | 1 (`CLINICAL_STAFF`) |

### Intervención 2: reglas de validación y bloqueo compartidas

**2a. Valores del catálogo de medicamentos.** `create_catalog_item` repetía en línea las reglas de concentración, stock y stock mínimo que `update_catalog_item` ya aplicaba con sus normalizadores privados.

- Protección previa: `src/medications/test_catalog_validation.py` (commit `8325e36`) comprueba que crear y actualizar rechazan los mismos valores con el mismo mensaje. Incluye valores límite: concentración `0.005`, que se redondea a `0.00` y se rechaza, y `0.006`, que se acepta como `0.01`; stock `0` se acepta y `-1` se rechaza.
- Refactor: `parse_concentration_mg`, `parse_stock` y `parse_min_stock_alert` (commit `b0f814c`). Ambos flujos usan ahora estas funciones.

**2b. Bloqueo de paciente activo.** Ocho operaciones repetían el mismo bloque: `select_for_update`, error 404 si el paciente no existe y error 409 si ya egresó. Cada una cambiaba solo el mensaje.

- Protección previa: `src/patients/test_active_patient_lock.py` (`ea15135`) fija el mensaje 409 de cada operación y el 404 para un id inexistente.
- Refactor: `patients/locks.py::lock_active_patient(patient_id, *, discharged_message)` (`57798e1`, `5a5b3d2`). Lo usan `patients`, `alerts` y `medications`.

| Indicador | Antes | Después |
|---|---|---|
| Copias de la regla "concentración > 0 / stock ≥ 0" | 2 (crear y actualizar) | 1 |
| Copias del bloqueo de paciente activo | 8 (3 apps) | 1 (`lock_active_patient`) |
| Lugares a editar para cambiar el mensaje 404 de paciente | 4 | 1 |

Nota: en las operaciones que antes usaban `.get(pk=...)`, un paciente borrado de forma concurrente ahora responde 404 en lugar de un error 500. Es el único cambio observable y es una mejora.

## 2. Interfaz del componente reutilizable: `accounts.roles.require_role`

| Aspecto | Definición |
|---|---|
| Nombre y propósito | `require_role(actor, allowed, message)`: exige que el actor tenga un rol permitido antes de ejecutar una operación de dominio. |
| Entrada | `actor: User` (o cualquier objeto con `role: str`), `allowed: Iterable[str]` (usar las constantes `ADMIN_ONLY`, `CLINICAL_STAFF`, `CLINICAL_OR_ADMIN`, `THRESHOLD_MANAGERS`, `CATALOG_MANAGERS`, `NEONATOLOGIST_ONLY`, …), `message: str` en español. |
| Salida | `None` si el rol está permitido. |
| Errores | `PermissionDomainError(message)`; el manejador global (`poki_koa/exceptions.py`) la traduce a HTTP 403 con `code = "permission_denied"`. |
| Complemento | `has_role(user, allowed) -> bool`, que no lanza excepción y acepta `None`; lo usan los permisos DRF. |
| Consumidores | Servicios de `patients`, `alerts`, `medications`, `devices`, `accounts` y `accounts/permissions.py`, todos con la misma implementación. |

Ejemplo de uso desde otro archivo:

```python
from accounts.roles import CLINICAL_STAFF, require_role

def registrar_algo(*, actor, ...):
    require_role(actor, CLINICAL_STAFF, "Solo el personal clínico puede registrar esto.")
    ...
```

Para comprobarlo, ejecutar `uv run python -m pytest src/accounts/test_roles.py src/accounts/test_role_guards.py`. Para verlo en funcionamiento: con `seed_demo` cargado, iniciar sesión como `matrona.diaz@pokikoa.cl` y hacer `POST /api/v1/patients/<id>/discharge/` con `{"outcome": "survived"}`. La respuesta es 403 `permission_denied` con el mensaje "Solo un Neonatólogo está autorizado para firmar el egreso clínico de un paciente.", verificado el 2026-11-11. En `POST /api/v1/cribs/` la petición la rechaza antes el permiso DRF `IsAdminRole`, que usa el mismo `ADMIN_ONLY`.

## 3. Organización de los repositorios

**Backend.** Cada aplicación de dominio separa sus capas: HTTP en `views.py` y `serializers.py`, negocio en `services.py`, datos en `models.py` y reglas puras en `rules.py`, `policies.py`, `schedule.py` y `validators.py`. Las reglas que comparten varias apps quedan en un solo módulo:

- `accounts/roles.py`: roles y guarda de rol.
- `patients/locks.py`: bloqueo de paciente activo.

El detalle y las operaciones públicas de cada módulo están en [ARCHITECTURE.md §2](ARCHITECTURE.md).

**Frontend.** La organización es la siguiente:

| Carpeta | Contenido |
|---|---|
| `api/` | Cliente HTTP y tipos generados |
| `api/mappers/` | Traducción del contrato a modelos de UI, incluidos los CSV de dominio `reporteACsv` y `registrosACsv` |
| `services/` | Solo llamadas HTTP |
| `hooks/queries/` | Caché y carga con TanStack Query |
| `utils/` | Funciones puras reutilizables: `csv.ts`, `estados.ts` |
| `pages/` | Presentación |

En este trabajo se aplicaron tres cambios:

- Se sacó la lógica CSV del servicio de reportes.
- Se centralizaron las reglas de estado "plan activo" e "indicación vigente".
- `ReportesPage` pasó de la carga manual a las consultas `useReporteQuery` y `useSerieQuery`.

El detalle está en `frontend/docs/ARQUITECTURA.md`.

## 4. Revisión de dependencia externa: drf-spectacular

| Criterio | Registro |
|---|---|
| Nombre y versión | `drf-spectacular` 0.30.0, fijada en `uv.lock` y publicada el 2026-07-06. `pyproject.toml` exige `>=0.30.0`. |
| Funcionalidad | Genera el contrato OpenAPI 3 desde las vistas y serializers DRF. Se usa en `/api/v1/schema/`, `/api/v1/docs/` y `openapi/schema.yml`. El frontend genera sus tipos (`src/api/schema.d.ts`) desde ese archivo con `openapi-typescript`. |
| Mantenimiento | Las versiones salen con regularidad: 0.28.0 (2024-11-30), 0.29.0 (2025-11-01) y 0.30.0 (2026-07-06), según el [changelog oficial](https://drf-spectacular.readthedocs.io/). [Repositorio](https://github.com/tfranzel/drf-spectacular). |
| Licencia y condiciones | BSD de 3 cláusulas ([documentación](https://drf-spectacular.readthedocs.io/en/latest/readme.html)). Obligación aplicable: al redistribuir el software hay que conservar el aviso de copyright y el texto de la licencia, y no se puede usar el nombre del autor para promocionar el producto. |
| Riesgo | Un cambio incompatible en el esquema generado al actualizar (nombres de componentes, enums, nulabilidad) rompería los tipos del frontend sin aviso. Probabilidad media (versiones 0.x sin garantía de API estable) e impacto alto (contrato entre los dos repos). |
| Medida | Versión fijada en `uv.lock` y actualizaciones solo con un PR propio. CI regenera el esquema con `--validate --fail-on-warn` y falla si difiere de `openapi/schema.yml`. Además, `src/poki_koa/test_openapi_contract.py` genera el esquema en memoria y comprueba las rutas y los campos que usa el frontend. |
| Cómo se comprueba la medida | `uv run python -m pytest src/poki_koa/test_openapi_contract.py`: en una actualización de la librería, la prueba o el paso "schema actualizado" de CI fallan antes de llegar a `rewrite/v2`. También se revisan los avisos de seguridad de la versión instalada en [Snyk](https://security.snyk.io/package/pip/drf-spectacular). |

## 5. Comandos y CI

```bash
# Backend
uv sync && uv run poki_koa migrate && uv run poki_koa seed_demo
uv run python -m pytest                           # suite completa
uv run ruff check src && uv run ruff format --check src
uv run python -m uvicorn poki_koa.asgi:application --app-dir src --reload

# Frontend
npm ci && npm run test:coverage && npm run lint && npm run build
npm run dev
```

| Repositorio | Pruebas antes | Pruebas después |
|---|---|---|
| Backend | 160 | 175 (pruebas nuevas: `accounts/test_roles.py`, `accounts/test_role_guards.py`, `medications/test_catalog_validation.py`, `patients/test_active_patient_lock.py`, `poki_koa/test_openapi_contract.py`) |
| Frontend | 102 | 119 (pruebas nuevas: `utils/csv.test.ts`, `utils/estados.test.ts`, `hooks/queries/reportes.test.ts`, casos en `api/mappers/reportes.test.ts` y `registros.test.ts`) |

CI:

- Backend: `.github/workflows/ci.yml` ejecuta ruff, migraciones, pytest con cobertura y la verificación de `openapi/schema.yml`.
- Frontend: `.github/workflows/ci.yml` ejecuta prettier, oxlint, build y vitest con cobertura.

_Enlaces a las ejecuciones de los PR `refactor/unidad-3`: pendientes._

## 6. Deuda pendiente

| Deuda | Motivo | Responsable | Condición de revisión |
|---|---|---|---|
| Carga manual de datos (`useState` + `Promise.allSettled`) en `DashboardPage`, `TurnosPage`, `RegistrosPage`, `MapaCunasPage`, `PlanesPage`, `AlertasPage`, `MedicamentosPage` y `MisCunasPage` | Se migró solo `ReportesPage` para validar el patrón sin arriesgar la entrega | _(integrante)_ | Al modificar cada página, migrarla a `hooks/queries/` |
| Funciones extensas en `patients/services.py` (`admit_patient`, `discharge_patient`) | Necesitan pruebas de caracterización de auditoría antes de dividirlas | _(integrante)_ | Antes de la siguiente funcionalidad en pacientes |
| Exportación de auditoría limitada a 100 registros | Límite `max_page_size` del backend | _(integrante)_ | Si se pide un export completo, crear un endpoint CSV en el backend |
| `jsqr ^1.4.0` en el frontend sin versiones recientes | Funciona para el lector QR actual | _(integrante)_ | Revisión trimestral de avisos o fallo del escáner |
