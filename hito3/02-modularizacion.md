# 02 · Modularización

## Organización elegida y por qué

**Combinada: por funcionalidades (dominios) y, dentro de cada dominio, por capas.**

- *Backend (Django + DRF):* una app por contexto clínico (`patients`, `alerts`, `vitals`…) porque el negocio cambia por funcionalidad, y dentro de cada app capas fijas, porque DRF ya separa vista, serializador y modelo.
- *Frontend (React):* por capas técnicas (`api`, `services`, `hooks`, `utils`, `pages`) y por pantalla en `pages/`, porque las pantallas comparten muchos servicios.

Ambos repos ya estaban modularizados; el Hito 3 revisó los límites y movió las reglas que seguían repartidas a un único módulo.

## Backend: responsabilidades

| Capa (archivo) | Responsabilidad | Regla de límite |
|---|---|---|
| `views.py` + `serializers.py` | HTTP: autenticación, permisos, formato | Sin lógica de negocio |
| `services.py` | Operaciones de dominio transaccionales y auditadas (API pública de la app) | Única capa que escribe |
| `models.py` | Esquema e invariantes | — |
| `rules.py`, `policies.py`, `schedule.py`, `validators.py` | Reglas puras, sin E/S | Una sola fuente por regla |
| `roles.py`, `locks.py` | **Reglas compartidas entre apps** (nuevas en el Hito 3) | Las consumen los `services.py` |

## Árbol antes y después (backend)

```text
ANTES (188dd74)                    DESPUÉS (main, 2.1.0)
src/accounts/                      src/accounts/
├── permissions.py                 ├── permissions.py   usa has_role + constantes
├── services.py                    ├── roles.py         NUEVO  require_role / has_role
└── tests.py                       ├── services.py
                                   ├── test_roles.py, test_role_guards.py   NUEVO
src/patients/                      src/patients/
├── services.py  (8 bloqueos)      ├── locks.py         NUEVO  lock_active_patient
└── tests.py                       ├── services.py     (llama a locks)
                                   └── test_active_patient_lock.py          NUEVO
src/medications/                   src/medications/
└── services.py  (validación x2)   ├── services.py     parse_concentration_mg / parse_stock / …
                                   └── test_catalog_validation.py           NUEVO
src/poki_koa/                      src/poki_koa/
└── exceptions.py                  ├── exceptions.py   (+ Http404 → not_found)
                                   ├── test_openapi_contract.py             NUEVO
                                   └── test_not_found_envelope.py           NUEVO
```

## Interfaces y dependencias (qué expone cada módulo)

| Módulo | Operaciones públicas | Quién lo llama |
|---|---|---|
| `accounts/roles.py` | `require_role(actor, allowed, message)`, `has_role(user, allowed)`, constantes de conjuntos | `services.py` de patients, alerts, medications, devices, accounts; `accounts/permissions.py` |
| `patients/locks.py` | `lock_active_patient(patient_id, *, discharged_message)` | `patients`, `alerts`, `medications` (8 llamadas) |
| `medications/services.py` | `parse_concentration_mg`, `parse_stock`, `parse_min_stock_alert` | `create_catalog_item` y `update_catalog_item` |
| `poki_koa/exceptions.py` | `DomainError` y subclases, `custom_exception_handler` | Todos los servicios; manejador global de DRF |

Sentido de las dependencias (nunca al revés): `views → services → (roles, locks, rules, audit, realtime) → models`. Las reglas puras no importan vistas ni modelos de otras apps.

## Caso representativo, antes y después

**Egreso de un paciente por una matrona** (`POST /api/v1/patients/<id>/discharge/`).

| | Antes (`188dd74`) | Después (`2.1.0`) |
|---|---|---|
| Dónde está la regla | Un `if actor.role not in {...}` dentro de `discharge_patient` | `require_role(actor, NEONATOLOGIST_ONLY, …)` en la misma función |
| Resultado | `403 permission_denied`, mensaje «Solo un Neonatólogo está autorizado para firmar el egreso clínico de un paciente.» | **Idéntico** (verificado el 2026-11-23, ver [04](04-integracion.md) caso 2) |
| Prueba que lo fija | `test_role_guards.py` (escrita antes del refactor) | La misma, sin cambios |

## Frontend

Ver [hito3 del frontend](https://github.com/PokiKoa/frontend/blob/main/hito3/01-intervencion-csv-y-modularizacion.md): `api/` (cliente y mappers), `services/` (solo HTTP), `hooks/queries/` (caché), `utils/` (funciones puras: `csv.ts`, `estados.ts`), `pages/` (presentación).

## Límites que quedan por mejorar

`patients/services.py` aún concentra funciones largas (`admit_patient`, `discharge_patient`); está registrado como deuda en [01 §6](01-diagnostico-e-intervenciones.md).
