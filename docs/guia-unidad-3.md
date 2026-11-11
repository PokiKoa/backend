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
| 2 | _En curso_ | | | | | |
| 3 | _Frontend, ver ficha del frontend_ | | | | | |

### Intervención 1: guarda de rol centralizada

- **Consecuencia del problema:** cambiar quién puede ejecutar una operación obligaba a editar varios archivos; los conjuntos de roles se escribían a mano en cada servicio y en los permisos DRF, y podían divergir.
- **Protección previa:** `src/accounts/test_role_guards.py` fija, para las 24 operaciones protegidas, los roles admitidos y el mensaje exacto de rechazo de cada rol no admitido. Se escribió y aprobó antes de tocar los servicios.
- **Pasos:** un commit por transformación: crear el módulo con su contrato, reemplazar la guarda app por app (suite completa tras cada una) y hacer que los permisos DRF usen las mismas constantes.

| Indicador | Antes | Después |
|---|---|---|
| Definiciones inline de la regla "rol permitido" | 24 en servicios + 5 en `permissions.py` | 1 (`accounts.roles.require_role` / `has_role`) |
| Lugares a editar para cambiar el conjunto "personal clínico" | 10 (9 guardas + `IsClinicalStaff`) | 1 (`CLINICAL_STAFF`) |

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
