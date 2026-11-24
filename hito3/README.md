# Hito 3 — Refactorización, modularización y entrega (ISF224)

Carpeta de estudio del Hito 3 de **Poki Koa**. Cubre los dos repositorios propios: [backend](https://github.com/PokiKoa/backend) (esta carpeta, informe principal) y [frontend](https://github.com/PokiKoa/frontend) (`hito3/` en su raíz, solo lo propio de la interfaz).

**Versión entregada: `2.1.0`** · 2026-11-23 · Orden de lectura recomendado: 01 → 06.

| # | Archivo | Qué responde | Criterio de la rúbrica |
|---|---|---|---|
| 01 | [Diagnóstico e intervenciones](01-diagnostico-e-intervenciones.md) | Qué problemas había, cómo se priorizaron y qué mejoró (2 indicadores) | 1 y 2 |
| 02 | [Modularización](02-modularizacion.md) | Cómo está organizado el código y dónde vive cada responsabilidad | 3 y 4 |
| 03 | [Componente reutilizable y dependencia](03-componente-y-dependencia.md) | Contrato de `require_role` y revisión de `drf-spectacular` | 5 |
| 04 | [Integración](04-integracion.md) | Diagrama del flujo y tres casos ejecutados (válido, inválido, recurso ausente) | 6 |
| 05 | [Entrega](05-entrega.md) | Versión, paquete, licencias, CI, cobertura y revisión externa | 6 y 7 |
| 06 | [Informe de cierre](06-informe-cierre.md) | Alcance, decisiones, mejoras y pendientes | 7 |

Frontend: [`hito3/` del frontend](https://github.com/PokiKoa/frontend/tree/main/hito3) (intervención 3 y modularización de la interfaz).

## Para una prueba rápida

```bash
cp .env.example .env && ./scripts/setup.sh       # levanta PostgreSQL y Redis, migra y carga datos ficticios
uv run pytest                                      # 217 pruebas
uv run coverage run -m pytest && uv run coverage report   # cobertura 95,2 %
```

El README de la raíz tiene los pasos completos y los problemas frecuentes.

## Estado honesto

- Todo lo marcado como «ejecutado» se corrió el 2026-11-23 con PostgreSQL 16 y Redis 7 reales (Docker); la salida está pegada tal cual en `04-integracion.md`.
- **Único punto pendiente:** la revisión del paquete por una persona de otro equipo (`05-entrega.md` §5). No se puede completar sin esa persona; la plantilla está lista.
