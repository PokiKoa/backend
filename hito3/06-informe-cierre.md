# 06 · Informe de cierre

**Alcance entregado.** Backend v2 (Django + DRF + Channels, monolito modular por dominios) y frontend React, versión `2.1.0`. Tres intervenciones de refactorización con pruebas, módulos compartidos con contrato, revisión de `drf-spectacular`, tres casos de integración ejecutados contra PostgreSQL y Redis reales, paquete con licencias y documentación en `hito3/`.

**Decisiones de construcción y sus efectos**

| Decisión | Efecto |
|---|---|
| Una sola fuente por regla (`roles.py`, `locks.py`, `parse_*`, `csv.ts`) | Cambiar una regla pasó de editar hasta 10 archivos a editar 1 |
| Escribir la prueba de caracterización **antes** de refactorizar | Cero cambios de comportamiento no previstos; el único observable (500 → 404) quedó documentado |
| Mantener la organización por dominios + capas | No hizo falta mover carpetas; se corrigieron solo los límites que fallaban |
| Contrato OpenAPI como frontera entre repos, validado en CI | Los tipos del frontend no se desfasan sin que algo falle |
| Subir a `2.1.0` en vez de mover `2.0.0` | No se reescribe historia publicada; versión coherente en paquete, tags y notas |

**Mejoras verificadas:** 24+5 → 0 guardas de rol duplicadas · 8 → 1 bloqueos de paciente · 1 → 2 consumidores del exportador CSV · 160 → 217 pruebas backend · 102 → 129 frontend · cobertura backend 95,2 % (≥ 90 % exigido) · casos 1–3 con resultado esperado = obtenido · un bug real (404 `api_error`) detectado por la verificación y corregido.

**Pendientes priorizados**

1. **Alta:** revisión del paquete por otro equipo ([05 §5](05-entrega.md)); sin ella el criterio 7 no llega al máximo.
2. **Alta:** cada integrante confirma su aporte en [01](01-diagnostico-e-intervenciones.md) antes de la Sumativa 3.
3. **Media:** Redis caído debe degradar sin 500 (`try/except` en `vitals/realtime.py`) y `health/ready` podría medir Redis.
4. **Media:** dividir `admit_patient`/`discharge_patient` y migrar las 8 páginas con carga manual a `hooks/queries/`.
5. **Baja:** endpoint CSV de auditoría sin límite de 100; revisar `jsqr` cada trimestre.
