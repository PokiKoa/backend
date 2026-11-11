
## Catálogo de Requisitos Extrafuncionales
Clasificación según ISO 25010 y tipo de restricción.
Prioridad: Alta, Media o Baja.

| ID | Tipo | Descripción | Prioridad |
|---|---|---|---|
| REF-01 | Calidad de servicio (Rendimiento) | El sistema debe responder en menos de 2 segundos para consultas de lectura y menos de 3 segundos para operaciones de escritura en condiciones normales. | Alta |
| REF-02 | Calidad de servicio (Disponibilidad) | El sistema debe estar disponible al menos el 99% del tiempo durante el horario laboral del servicio de neonatología. | Alta |
| REF-03 | Calidad de servicio (Seguridad) | Autenticación obligatoria mediante tokens JWT y control de acceso por roles (Matrona, Médico, Administrador) para todas las operaciones con datos clínicos. | Alta |
| REF-04 | Calidad de servicio (Seguridad) | Las comunicaciones cliente-servidor deben ir cifradas con HTTPS/TLS. Los secretos y credenciales se manejan mediante variables de entorno (.env). | Alta |
| REF-05 | Calidad de servicio (Confiabilidad) | El sistema debe generar alertas automáticas cuando los signos vitales estén fuera de rango seguro, sin perder eventos críticos. | Alta |
| REF-06 | Calidad de servicio (Usabilidad) | La interfaz debe usar colores y jerarquía visual clara para que el personal identifique rápidamente el estado de cada cuna. | Media |
| REF-07 | Calidad de servicio (Mantenibilidad) | Arquitectura modular con API REST y separación de capas, que permita mantenimiento y pruebas independientes. | Media |
| REF-08 | Restricción técnica (Frontend) | Interfaz SPA desarrollada con React, TypeScript y Vite, compatible con navegadores modernos (Chrome, Firefox, Edge, Safari). | Media |
| REF-09 | Restricción técnica (Backend) | Backend en Python 3.10+ con Django y Django REST Framework, exponiendo endpoints RESTful con formato JSON. | Alta |
| REF-10 | Restricción técnica (Base de datos) | Base de datos relacional con soporte para transacciones ACID, usando SQLite en desarrollo y PostgreSQL en producción, a través del ORM de Django. | Alta |
| REF-11 | Restricción de proyecto (Trazabilidad) | Control de versiones con Git/GitHub, manteniendo trazabilidad entre commits, issues y pull requests. | Alta |
| REF-12 | Otros (Idioma) | Toda la interfaz, mensajes y terminología clínica deben estar en español. | Baja |

> [!IMPORTANT]
> Los requisitos de prioridad **Alta** (REF-01 a REF-05, REF-09, REF-10, REF-11) son abordados de forma explícita en las decisiones de diseño arquitectónico en [Arquitectura](Arquitectura.md).

### Verificación de requisitos prioritarios

El catálogo define objetivos del sistema; su inclusión no acredita cumplimiento.
Las pruebas funcionales de las APIs no sustituyen las siguientes verificaciones:

| Requisitos | Evidencia necesaria |
|---|---|
| REF-01 | Medir tiempos de lectura y escritura, registrando volumen de datos, concurrencia y entorno para definir las condiciones normales. |
| REF-02 | Registrar tiempo disponible y tiempo total del horario evaluado; comprobar una proporción de al menos 99%. |
| REF-03 y REF-04 | Probar rechazo de accesos sin autenticación o sin permisos, verificar HTTPS y comprobar que los secretos se cargan desde el entorno. |
| REF-05 | Probar generación, persistencia y consulta de alertas ante valores fuera de rango; evaluar recuperación ante fallos antes de afirmar que no se pierden eventos. |
| REF-09 y REF-10 | Verificar el stack declarado, las respuestas JSON y el comportamiento de las transacciones en la base utilizada. La validación en SQLite no acredita PostgreSQL. |
| REF-11 | Seguir el vínculo entre historia, rama, PR y commit de integración en GitHub. |
