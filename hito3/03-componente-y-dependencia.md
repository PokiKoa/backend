# 03 · Componente reutilizable y dependencia externa

## A. Componente propio: `accounts.roles.require_role`

| Aspecto | Definición |
|---|---|
| **Nombre y propósito** | `require_role(actor, allowed, message)`: exige que quien ejecuta una operación tenga un rol permitido, antes de tocar datos. |
| **Entrada** | `actor: User` (o cualquier objeto con `.role: str`); `allowed: Iterable[str]` (usar constantes: `ADMIN_ONLY`, `CLINICAL_STAFF`, `CLINICAL_OR_ADMIN`, `THRESHOLD_MANAGERS`, `CATALOG_MANAGERS`, `NEONATOLOGIST_ONLY`…); `message: str` en español. |
| **Salida** | `None` si el rol está permitido. |
| **Errores** | `PermissionDomainError(message)` → el manejador global la responde como **403** con `{"error": {"code": "permission_denied", "message": …}}`. |
| **Complemento** | `has_role(user, allowed) -> bool`: no lanza excepción y acepta `None`; lo usan los permisos DRF. |
| **Consumidores reales** | 27 llamadas en los servicios de `patients`, `alerts`, `medications`, `devices`, `accounts` + `accounts/permissions.py`. Todos usan la misma implementación. |

**Ejemplo desde otro archivo**

```python
from accounts.roles import CLINICAL_STAFF, require_role

def registrar_algo(*, actor, ...):
    require_role(actor, CLINICAL_STAFF, "Solo el personal clínico puede registrar esto.")
    ...
```

**Cómo comprobarlo**

```bash
uv run pytest src/accounts/test_roles.py src/accounts/test_role_guards.py
```

Y en vivo: iniciar sesión como `matrona.diaz` y hacer `POST /api/v1/patients/1/discharge/` → 403 (caso 2 de [04](04-integracion.md)). El contrato se conserva si cambia la implementación interna: `test_role_guards.py` fija los roles admitidos y el mensaje exacto de las 24 operaciones.

**Segundo componente (frontend):** `toCsv` / `downloadCsv`, documentado en el [hito3 del frontend](https://github.com/PokiKoa/frontend/blob/main/hito3/01-intervencion-csv-y-modularizacion.md).

## B. Dependencia externa: `drf-spectacular`

| Criterio | Registro |
|---|---|
| **Nombre y versión** | `drf-spectacular` **0.30.0** (fijada en `uv.lock`; `pyproject.toml` pide `>=0.30.0`) |
| **Qué resuelve y dónde se usa** | Genera el contrato OpenAPI 3 desde vistas y serializers. Se usa en `/api/v1/schema/`, `/api/v1/docs/` y `openapi/schema.yml`; el frontend genera sus tipos (`src/api/schema.d.ts`) a partir de ese archivo. |
| **Mantenimiento** | Versiones regulares: 0.28.0 (2024-11), 0.29.0 (2025-11), 0.30.0 (2026-07). [Repositorio](https://github.com/tfranzel/drf-spectacular) · [documentación](https://drf-spectacular.readthedocs.io/) |
| **Licencia** | BSD de 3 cláusulas ([texto](https://github.com/tfranzel/drf-spectacular/blob/master/LICENSE)). *Obligación aplicable:* al redistribuir, conservar el aviso de copyright y el texto de la licencia; no usar el nombre del autor para promocionar el producto. Registrada en [`THIRD_PARTY_LICENSES.md`](../THIRD_PARTY_LICENSES.md). |
| **Riesgo** | Una actualización cambia el esquema generado (nombres de componentes, enums, nulabilidad) y rompe los tipos del frontend sin aviso. **Probabilidad media** (versiones 0.x), **impacto alto** (contrato entre los dos repos). |
| **Mitigación** | Versión fijada en `uv.lock`, actualizaciones solo con PR propio y CI que regenera el esquema con `--validate --fail-on-warn` y falla si difiere de `openapi/schema.yml`. Además `src/poki_koa/test_openapi_contract.py` comprueba rutas y campos que usa el frontend. |
| **Cómo se comprobó** | Ejemplo ejecutable: `uv run poki_koa spectacular --validate --fail-on-warn --file /tmp/schema.yml && diff /tmp/schema.yml openapi/schema.yml` (sin diferencias el 2026-11-23) y `uv run pytest src/poki_koa/test_openapi_contract.py`. |
