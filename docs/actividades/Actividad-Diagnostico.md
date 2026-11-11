## Diagnostico

| Área de proceso | Grado | Evidencia |
|---|:---:|---|
| Gestión de requisitos | P | Tenemos los no funcionales bien listados ([Requisitos extrafuncionales](../proyecto/ReqExtrafuncionales.md)), pero los funcionales son puros issues sueltos, sin plantilla ni criterio de aceptación |
| Planificación del proyecto | P | Trabajamos por ramas y PRs, se ve harto movimiento, pero no hay sprints, fechas ni estimación con datos, se avanza "a feature libre" |
| Gestión de la configuración | L | Convención de ramas (feat/fix/docs) y 21 PRs mergeados, ordenado. Falta poner tags de versión aunque el pyproject ya dice 0.1.0 |
| Verificación | L | Hay tests reales (modelos + endpoint bebés) y ruff como linter. Pero nadie los corre automático, no hay CI, depende de que cada uno se acuerde |

**Nivel:** vamos como en transición al Nivel 2, no llegamos del todo, nos falta amarrar requisitos con criterios y meter algo de planificación con plazos reales, el resto ya lo tenemos bastante encaminado.

### Propuesta de Acciones de Mejora (Nivel 2 de Madurez)

| Campo | Acción 1 (Gestión de Requisitos) | Acción 2 (Planificación del Proyecto) |
| :--- | :--- | :--- |
| **Brecha** | Requisitos funcionales en *issues* sueltos, sin plantilla estándar ni criterios de aceptación definidos. | Desarrollo sin ciclos fijados ("a feature libre"), sin estimación basada en datos, ni plazos u objetivos temporales definidos. |
| **Acción** | A partir de la próxima iteración, todo *issue* funcional deberá crearse utilizando una plantilla obligatoria que exija al menos un criterio de aceptación en formato *Given/When/Then* para ser considerado en el *backlog*. | Agrupar las tareas en sprints de 2 semanas, asignando una estimación en puntos o horas a cada *issue* y fijando una fecha de entrega clara para la iteración. |
| **Responsable y plazo** | Mauricio Escobar — Inicio en el próximo sprint (duración de 2 sprints). | Mauricio Escobar — Inicio en el próximo sprint (duración de 2 sprints). |
| **Evidencia esperada** | Plantilla de *issue* (template) en el repositorio/tablero y tarjetas del sprint que contengan el apartado de criterios de aceptación completado. | *Project Board* configurado con las fechas de inicio/fin del sprint y las historias/issues estimadas y asignadas. |
| **Indicador** | Porcentaje de historias/issues reabiertas o devueltas por mala definición (reducir a menos del 10% en dos sprints). | Porcentaje de cumplimiento de lo planificado (lograr una desviación menor al 15% entre los puntos/horas estimadas y completadas al finalizar el sprint). |

---

#### Cumplimiento de Condiciones:
1. **Brechas distintas:** La Acción 1 aborda la falta de definición y criterios en los requisitos, mientras que la Acción 2 resuelve la falta de orden, plazos y estimación en la planificación.
2. **Sin costo ni personal adicional:** Se aprovechan herramientas como *Issue Templates* de GitHub.
3. **Métricas con datos actuales:** Utiliza el seguimiento básico de los *issues* (estado abierto/cerrado/reabierto) y la comparación de horas/puntos del sprint.