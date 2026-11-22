# Modelado UML — Poki Koa

Esta carpeta documenta la implementación disponible en los repositorios `PokiKoa/backend` y `PokiKoa/frontend`. Los diagramas se expresan como código Mermaid para conservar una fuente editable y revisable en Git.

## Diagramas

1. [Casos de uso](1-casos-de-uso.md): actores humanos y dispositivo IoT, frontera del sistema y cobertura funcional.
2. [Clases](2-clases.md): entidades persistentes del dominio, atributos tipados, visibilidad y multiplicidades.
3. [Secuencia](3-secuencia.md): ingesta de telemetría, evaluación de alertas y difusión en tiempo real.
4. [Componentes](4-componentes.md): frontend, API, módulos de dominio, WebSocket, persistencia y servicios externos.

## Nota de lectura general

Los diagramas representan el sistema implementado y no una arquitectura futura. El backend está organizado como monolito modular Django/DRF; el frontend React/TypeScript consume su API REST y sus canales WebSocket. La entidad `Patient` es el concepto transversal elegido para comprobar coherencia: aparece como objetivo de las acciones clínicas, se relaciona con lecturas, alertas, planes y prescripciones, y se propaga desde los servicios del backend hasta la interfaz. Los elementos marcados como externos corresponden a infraestructura o dispositivos que interactúan con la aplicación, no a clases internas.

## Alcance y límites

La vista de clases prioriza entidades persistentes centrales del dominio; no intenta convertir cada serializer, vista, DTO o helper en clase de negocio. Los actores representan roles y dispositivos identificados en el código. La integración con PostgreSQL, Redis y Django Channels se muestra en componentes porque forma parte de la arquitectura desplegada.

## Fuentes de contraste

- `backend/docs/ARCHITECTURE.md`
- `backend/docs/DATA_SCHEMA.md`
- `backend/docs/SECURITY_AND_RBAC.md`
- `backend/src/*/models.py`, `services.py`, `views.py`
- `frontend/src/routes/AppRouter.tsx` y `frontend/src/services/*.ts`
