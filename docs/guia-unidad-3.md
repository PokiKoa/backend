# Guía Unidad 3: refactorización, modularización y reutilización

Ficha de evidencias para la Sumativa 3 (ISF224). Cubre los dos repositorios de la solución:

- Backend: [poki-koa-backend](https://github.com/Asulx/poki-koa-backend), rama `refactor/unidad-3`.
- Frontend: repositorio `frontend`, rama `refactor/unidad-3`, con su ficha en `docs/guia-unidad-3.md`.

> Estado: **en progreso**. Esta ficha se actualiza al cerrar cada paso.

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
| _Pendiente: p. ej. enfermera intenta crear una cuna → HTTP 403 con mensaje_ | _(integrante)_ | | |

## 1. Intervenciones

| # | Problema o necesidad | Ubicación | Prioridad | Solución | Responsable | Commits |
|---|---|---|---|---|---|---|
| 1 | Regla de permisos por rol duplicada (24 copias de `if actor.role not in {...}: raise PermissionDomainError`) | `src/{patients,alerts,medications,devices,accounts}/services.py` y `accounts/permissions.py` | Alta | Módulo `accounts/roles.py` con conjuntos de roles y `require_role` | _(integrante)_ | `2381602` (test), `59374af` (feat), `c06c1c5`…`92ade98` (refactor por app), `380191e` |
| 2 | Validaciones duplicadas en el catálogo y bloqueo de paciente activo repetido | `src/medications/services.py`, `src/patients/services.py`, `src/alerts/services.py` | Media | Funciones `parse_*` del catálogo y módulo `patients/locks.py` con `lock_active_patient` | _(integrante)_ | ver detalle |
| 3 | _Frontend, ver ficha del frontend_ | | | | | |

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

Para comprobarlo, ejecutar `uv run python -m pytest src/accounts/test_roles.py src/accounts/test_role_guards.py`. Para verlo en funcionamiento, iniciar sesión como `nurse` y hacer `POST /api/v1/cribs/`: la respuesta es 403 con el mensaje "Solo un administrador puede registrar nuevas cunas en el sistema."

## 3. Organización de los repositorios

_Pendiente: se completa al cerrar la modularización._

## 4. Revisión de dependencia externa

_Pendiente (drf-spectacular)._

## 5. Comandos y CI

```bash
uv run python -m pytest          # suite completa
uv run ruff check src && uv run ruff format --check src
```

CI: `.github/workflows/ci.yml` (ruff, migraciones, pytest con cobertura y verificación de `openapi/schema.yml`). _Enlace a la ejecución del PR pendiente._

## 6. Deuda pendiente

_Pendiente._
