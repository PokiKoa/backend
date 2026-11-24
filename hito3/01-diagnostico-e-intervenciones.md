# 01 · Diagnóstico e intervenciones

Se revisó el código del Hito 2 buscando reglas duplicadas, funciones extensas y responsabilidades mezcladas. Se encontraron más de tres problemas; se intervinieron los tres de mayor impacto y se postergó el resto (§4).

## 1. Las tres intervenciones

| # | Problema | Dónde | Consecuencia | Prioridad | Solución | Commits / PR |
|---|---|---|---|---|---|---|
| 1 | La regla «¿este rol puede hacer esto?» estaba copiada 24 veces | `src/{patients,alerts,medications,devices,accounts}/services.py` y `accounts/permissions.py` | Cambiar quién puede una operación obligaba a editar varios archivos y los conjuntos de roles podían divergir | **Alta** | Módulo `accounts/roles.py` con `require_role` y `has_role` | `2381602` (prueba), `59374af` (módulo), refactor por app, [PR #84](https://github.com/PokiKoa/backend/pull/84); remate en [PR #110](https://github.com/PokiKoa/backend/pull/110) |
| 2 | (a) Validación de concentración/stock repetida en crear y actualizar medicamento. (b) El bloque «bloquear paciente activo» repetido en 8 operaciones | `medications/services.py`, `patients/services.py`, `alerts/services.py` | Mensajes y reglas que podían desalinearse; un paciente borrado en paralelo producía error 500 | Media | `parse_concentration_mg`, `parse_stock`, `parse_min_stock_alert` y `patients/locks.py::lock_active_patient` | `8325e36`, `b0f814c` (a); `ea15135`, `57798e1`, `5a5b3d2` (b); PR #84 |
| 3 | Reportes mezclaba HTTP, generación de CSV y descarga; la auditoría no se podía exportar | Frontend: `services/reportesService.ts`, `pages/registros/RegistrosPage.tsx` | Lógica CSV imposible de reutilizar y sin pruebas propias | Media | `utils/csv.ts` (`toCsv`, `downloadCsv`) con dos consumidores | Frontend `00ff6ac`…`5c2e8bd`, [PR #103](https://github.com/PokiKoa/frontend/pull/103). Detalle en el [hito3 del frontend](https://github.com/PokiKoa/frontend/blob/main/hito3/01-intervencion-csv-y-modularizacion.md) |

> **Responsables:** aún no definidos; se agregarán cuando cada integrante confirme su aporte.

## 2. Por qué esa prioridad (impacto y esfuerzo)

| Intervención | Impacto medido | Esfuerzo | Resultado |
|---|---|---|---|
| 1 | 24 definiciones en servicios + 5 en permisos | Bajo: un módulo y sustitución mecánica | Alta |
| 2 | 8 bloqueos repetidos en 3 apps; 2 copias de validación | Medio: requirió pruebas de caracterización antes de extraer | Media |
| 3 | 1 flujo de exportación → 2 consumidores | Bajo: función pura y dos cambios de llamada | Media |

## 3. Antes y después (dos indicadores por intervención)

| Intervención | Indicador | Antes | Después (verificado en `main`) |
|---|---|---|---|
| 1 | Definiciones inline de la regla de rol | 24 + 5 | **0** inline; 27 llamadas a `require_role`, 1 implementación |
| 1 | Archivos a editar para cambiar «personal clínico» | 10 | **1** (`CLINICAL_STAFF`) |
| 2 | Copias del bloqueo de paciente activo | 8 (3 apps) | **1** (`lock_active_patient`, 8 llamadas) |
| 2 | Copias de la regla «concentración > 0 / stock ≥ 0» | 2 | **1** (3 funciones `parse_*`) |
| 3 | Implementaciones de escapado CSV | 1, acoplada al servicio | 1 en `utils/csv.ts`, sin E/S |
| 3 | Flujos que exportan CSV | 1 | **2** con la misma implementación |

*Cómo reproducir el conteo:* `grep -rn "role not in" src --include=*.py | grep -v test` (quedan 2 coincidencias, ambas validan valores de rol, no son la guarda) y `grep -rn "require_role(" src --include=*.py | grep -v test`.

## 4. Cómo se trabajó (pasos pequeños)

1. Rama propia y suite verde antes de editar (línea base: 160 pruebas backend, 102 frontend).
2. Un integrante distinto del autor comprobó el comportamiento inicial de la operación intervenida: egreso de un paciente por una matrona → `403 permission_denied` (revisor: Mauricio Escobar, 2026-11-11).
3. **Primero la prueba de caracterización** (`test_role_guards.py`, `test_catalog_validation.py`, `test_active_patient_lock.py`), después el cambio.
4. Un commit por transformación; suite completa tras cada una. Los commits de refactor (`refactor:`) están separados de los de comportamiento (`fix:`, `feat:`).

Único cambio observable de la intervención 2: operar sobre un paciente borrado en paralelo pasa de **500 a 404** (mejora, cubierta por prueba).

## 5. Corrección hallada durante el cierre

Al ejecutar el caso 3 de integración (ver [04](04-integracion.md)) un 404 respondía `code: "api_error"` en lugar de `not_found`, porque `Http404` de Django no estaba mapeado en el manejador global. Se corrigió en un commit aparte (`38aab4b`, `fix(api)`) con la prueba `poki_koa/test_not_found_envelope.py`. No es refactor: cambia el código de error de un 404 (el status HTTP no cambia).

## 6. Deuda postergada

| Deuda | Motivo | Cuándo se revisa |
|---|---|---|
| Carga manual de datos (`useState` + `Promise.allSettled`) en 8 páginas del frontend | Solo se migró `ReportesPage` para validar el patrón | Al tocar cada página, migrarla a `hooks/queries/` |
| `admit_patient` y `discharge_patient` extensas (`patients/services.py`) | Necesitan pruebas de caracterización de auditoría antes de dividirlas | Antes de la próxima funcionalidad de pacientes |
| Exportación de auditoría limitada a 100 filas | `max_page_size` del backend | Si se pide export completo: endpoint CSV en backend |
| `jsqr` sin versiones recientes | Funciona para el lector QR actual | Revisión trimestral o fallo del escáner |
| Redis caído: `group_send` sin `try/except` | Ver [04 §4](04-integracion.md); la telemetría respondería 500 | Antes de operar con monitores reales |
