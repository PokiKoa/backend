# Conversación con Clarita Reviews

[Chat compartido](https://chatgpt.com/share/6ad05d09-6e64-83e9-8e7e-b441ce2b35c6)

### Usuario

Te entregaremos distintas historias de usuario para que realices una revisión a cada una, realiza las observaciones necesarias y comenta lo que tenga que aplicarse.

Primera:

#### US-01 — Issue [#15](https://github.com/Asulx/poki-koa-web/issues/15)
Desarrollar formulario de gestión de pacientes (Registro y Edición)
Última actualización del issue: 2026-09-29T08:08:01Z.

#### Descripcion Historia

Como usuario del sistema (personal médico o administrativo) quiero contar con un formulario validado para el registro y edición de pacientes para poder ingresar y mantener actualizada su información sin cometer errores en los datos.

#### Criterios de aceptación

- Se implementó el componente del formulario para el registro de nuevos pacientes.
- Se adaptó el mismo formulario (o se creó uno equivalente) para la edición, el cual permite precargar los datos de un paciente existente.
- Se aplicaron validaciones en tiempo real (ej. campos obligatorios, formato correcto de correo electrónico, formato de RUT/DNI o teléfono).
 La interfaz muestra mensajes de error claros debajo de cada campo cuando no se cumple una validación.
 El botón de "Guardar" se deshabilita mientras existan errores en el formulario o mientras se esté procesando la petición (loading state).
…

### Clarita

¡Hola! Soy Clarita Reviews. Gracias por compartir la primera historia de usuario, US-01 — Issue [#15](https://github.com/Asulx/poki-koa-web/issues/15): Gestión de pacientes.

He identificado tanto la historia de usuario como sus cinco criterios de aceptación.

#### Revisión preliminar

La historia presenta una estructura adecuada: identifica un rol, una necesidad y un beneficio. Además, los criterios de aceptación contemplan funcionalidades importantes, como el registro, la edición y la validación de información.

Antes de realizar la revisión completa, hay algunos aspectos que conviene considerar:

- Rol: Se mencionan usuarios médicos y administrativos. Será importante confirmar si ambos tienen los mismos permisos y necesidades.

- Alcance: La historia reúne el registro y la edición de pacientes. Conviene evaluar si representan una única necesidad funcional o si deberían abordarse por separado.

- Criterios de aceptación: Están redactados principalmente como tareas implementadas. Será necesario revisar si expresan comportamientos verificables desde la perspectiva del usuario.

#### Información necesaria para continuar

Para evaluar correctamente la historia, necesito conocer el modelo verbal de la solución informática.

Este modelo debe describir cómo el sistema de gestión de pacientes funcionará, qué procesos permitirá realizar y cómo interactuarán con él los distintos usuarios.

Es importante porque nos permitirá determinar si la US-01 y sus criterios de aceptación son coherentes con el alcance real del proyecto, siguiendo los lineamientos de los documentos de referencia.

¿Ya tienen definido el modelo verbal de la solución informática? Si lo comparten, podremos revisar esta primera historia con observaciones concretas y recomendaciones de mejora, y después continuar con las siguientes.

### Usuario

Ya tenemos definido el modelo verbal de gestión de pacientes de Poki Koa. Te lo resumo para que revisemos la US-01:

¿Qué hace?
 Centraliza los datos clínicos y demográficos de los recién nacidos en la UCI Neonatal. Cada bebé registrado es el eje del sistema: a él se asocian su cuna con telemetría en tiempo real, su neonatólogo responsable y su esquema de medicación.

¿Qué permite hacer?

- Admisión: registrar al bebé con ID único (ej. BEB-0001), nombre, sexo, edad, edad gestacional, peso al nacer y fecha de ingreso.
- Actualización: editar peso, diagnóstico, observaciones y plan de cuidados.
- Asignación: vincular o reasignar médico y cuna.
- Consulta: ver estado, signos vitales, alertas y medicamentos administrados.
- Egreso: cerrar la internación, liberar la cuna y conservar el historial.

¿Quién lo usa y para qué?

- Admisión: ingresa los datos de filiación. El sistema valida campos obligatorios, ID no duplicado y peso positivo.
- Neonatólogos: consultan sus pacientes y registran diagnósticos y plan de cuidados.
- Enfermería y matronas: verifican la identidad del bebé antes de medicar o asociarlo a los sensores de la cuna.

¿Cómo se implementa?

- Frontend (React SPA): formularios con validación en tiempo real, estados de carga, guardado deshabilitado si hay errores y mensajes claros.
- Backend (Django REST): endpoints en /api/bebes/ (POST, GET, PATCH/PUT, DELETE), con validación de unicidad y formato, y respuestas HTTP estándar (201, 400, 404).

…

### Clarita

¡Perfecto! Ahora contamos con el modelo verbal de la solución informática de Poki Koa, por lo que podemos revisar la US-01 considerando las funcionalidades, los roles y las reglas de negocio del sistema.
Revisión de US-01 — Issue [#15](https://github.com/Asulx/poki-koa-web/issues/15)

Título actual: Desarrollar formulario de gestión de pacientes (Registro y Edición)
Requiere ajustes

La historia tiene una intención funcional clara y un beneficio identificable. Sin embargo, presenta algunas oportunidades de mejora para alinearse con el modelo verbal.

#### 1. Observaciones sobre la historia de usuario

| Aspecto | Observación |
| --- | --- |
| Título | Es demasiado extenso y está orientado al desarrollo de una interfaz. Se recomienda utilizar nombres funcionales breves, como Registrar paciente o Editar paciente. |
| Rol | "Usuario del sistema (personal médico o administrativo)" es demasiado general. El modelo verbal establece responsabilidades diferentes para admisión y neonatólogos. |
| Funcionalidad | Se agrupan dos acciones: registrar y editar pacientes. Conviene evaluar si pueden convertirse en historias independientes. |
| Beneficio | Es comprensible, pero podría enfocarse más en el valor clínico o administrativo de mantener información confiable. |
| Alcance | No se distingue qué información puede registrar o modificar cada rol. |

Recomendación principal: Evaluar la separación del registro y la edición de pacientes, ya que tienen objetivos, permisos y escenarios de validación diferentes.
#### 2. Observaciones sobre los criterios de aceptación

| Criterio | Evaluación | Observación |
| --- | --- | --- |
| CA1. Formulario de registro | Mejorar | Describe una tarea implementada, pero no especifica qué debe ocurrir cuando se registra correctamente un bebé. |
| CA2. Formulario de edición | Mejorar | La precarga es pertinente, pero falta verificar que las modificaciones se guarden y puedan consultarse posteriormente. |
| CA3. Validaciones | Mejorar | Los ejemplos de correo, RUT/DNI y teléfono no coinciden necesariamente con los datos del recién nacido definidos en el modelo verbal. |
| CA4. Mensajes de error | Adecuado | Es verificable. Conviene relacionar cada mensaje con la validación correspondiente. |
| CA5. Botón Guardar | Adecuado | Es verificable y coherente con el modelo. Conviene precisar cuándo vuelve a habilitarse. |

#### 3. Escenarios que faltan considerar

Según el modelo verbal, sería conveniente revisar la cobertura de los siguientes comportamientos:

- Identificación única: impedir el registro de bebés con identificadores duplicados.

- Peso válido: rechazar valores de peso iguales o inferiores a cero.

- Campos obligatorios: identificar exactamente cuáles son necesarios durante la admisión.

- Registro exitoso: confirmar que los datos del recién nacido quedaron almacenados correctamente.

- Actualización exitosa: verificar que los cambios autorizados se conserven.

- Errores de guardado: definir el comportamiento cuando el sistema no consigue registrar o actualizar la información.

Estos escenarios pueden expresarse utilizando la estructura Dado – Cuando – Entonces, que facilita comprobar los resultados esperados.
#### 4. Coherencia con Poki Koa

Hay dos decisiones funcionales que deberían aclararse antes de aprobar esta historia.

Primera: el modelo verbal distingue la admisión inicial de la actualización clínica. Por ello, es importante establecer si el personal administrativo puede modificar información clínica o si esa responsabilidad corresponde exclusivamente a los neonatólogos.

Segunda: los criterios actuales mencionan datos genéricos de pacientes, mientras que Poki Koa está orientado específicamente a recién nacidos de la UCI Neonatal. Las validaciones deben corresponder a esa población y a los campos realmente definidos.

#### Resultado de la revisión

Historia de usuario
Requiere ajustes

#### Criterios de aceptación

Requieren ajustes

Coherencia con el modelo verbal
Parcialmente alineada

Conclusión: La US-01 tiene una base funcional adecuada, pero todavía no está lista para considerarse completamente validada. Las principales mejoras son delimitar los roles, revisar la separación entre registro y edición, y completar los escenarios de aceptación con las reglas específicas de Poki Koa.

Una pregunta para continuar: ¿Prefieren mantener el registro y la edición de pacientes en una sola historia de usuario o están dispuestos a separarlos en dos historias independientes?

### Usuario

En una sola historia.

### Clarita

¡Perfecto! Mantendremos el registro y la edición de pacientes en una sola historia de usuario (US-01).

Esta decisión es válida, ya que ambas funcionalidades trabajan sobre la información de un mismo paciente y pueden compartir el formulario.

#### Ajustes recomendados para la US-01

1. Título: Simplificarlo a Gestionar pacientes, utilizando un verbo en infinitivo y un objeto directo.
2. Rol: Precisar qué usuarios pueden registrar y editar información. Según el modelo verbal, admisión y neonatólogos tienen responsabilidades diferentes.
3. Descripción: Mantener ambas funcionalidades, pero enfocarse en la necesidad del usuario y no en la implementación del formulario.
#### 4. Criterios de aceptación: Conservar los cinco criterios existentes, ajustando su redacción para que describan comportamientos verificables mediante el formato Dado – Cuando – Entonces.
5. Cobertura funcional: Incorporar los escenarios de registro exitoso, edición exitosa, campos obligatorios, identificadores duplicados, peso inválido y errores al guardar.

#### Resultado

US-01: Aprobada en alcance, pendiente de ajustes de redacción y criterios de aceptación.

No es necesario dividirla, aunque conviene comprobar que su tamaño permita desarrollarla y probarla dentro de un sprint.

Antes de cerrar la revisión: ¿El personal de admisión podrá registrar y editar todos los datos del paciente, o los neonatólogos serán los únicos autorizados para modificar la información clínica?

### Usuario

Solo el personal medico, neonatólogos/matronas

### Clarita

¡Perfecto! Con esta aclaración podemos precisar mejor el alcance de la US-01 — Gestionar pacientes de Poki Koa.

#### Ajuste de la revisión

Rol: El personal médico, específicamente neonatólogos y matronas, será el responsable del registro y la edición de pacientes.

Esto permite resolver una de las principales observaciones de la historia original: el rol era demasiado general.

#### Observaciones que todavía deben aplicarse

1. Descripción de la HU: Sustituir el rol genérico por los roles médicos autorizados. El beneficio de mantener información actualizada y evitar errores es adecuado.
#### 2. Criterios de aceptación: Incorporar la validación de permisos para impedir que usuarios no autorizados registren o editen pacientes.
3. Validaciones: Alinear los campos obligatorios con los datos neonatales definidos en el modelo verbal, especialmente el identificador único y el peso positivo.
4. Registro y edición: Mantener ambas operaciones dentro de la misma historia, diferenciando sus escenarios de aceptación.

#### Estado actualizado

US-01 — Gestionar pacientes
Pendiente de ajustes menores

La historia ya tiene un alcance definido y roles identificados. Solo queda mejorar la precisión de sus criterios de aceptación para que sean completamente verificables.

¿Deseas que demos por finalizada la revisión de la US-01 con estas observaciones y continuemos con la US-02?

### Usuario

Continuamos con la siguiente issue, desde ahora en adelante, solo realiza una revisión concreta para aplicarla de inmediato sin preguntas constantes (me voy a quedar sin tokens):

### Usuario

#### US-02 — Issue [#17](https://github.com/Asulx/poki-koa-web/issues/17)
Desarrollar formulario de gestión de medicamentos (Registro y Modificación)
Última actualización del issue: 2026-09-02T20:36:57Z.
Descripcion Historia
Como usuario del sistema (farmacéutico o administrador), quiero contar con un formulario interactivo y validado para registrar y modificar medicamentos para mantener el catálogo actualizado y evitar errores críticos en el ingreso de datos (como dosis o stock incorrecto).
Criterios de aceptación
- Se implementó el componente de formulario para el registro de un nuevo medicamento, incluyendo los campos clave (ej. nombre, principio activo, miligramos/dosis, cantidad en stock).
- Se adaptó el formulario para permitir la modificación de un medicamento existente, precargando correctamente sus datos actuales.
- Se aplicaron validaciones de datos en tiempo real (ej. campos obligatorios, números positivos para el stock y dosis).
 La interfaz despliega mensajes de error claros y específicos debajo de los campos que no superan la validación.
 El botón de acción ("Guardar" o "Registrar") se deshabilita si el formulario contiene errores o si se encuentra en estado de carga (loading).
…

### Clarita

#### Revisión US-02 — Issue [#17](https://github.com/Asulx/poki-koa-web/issues/17): Gestión de medicamentos

Estado: Requiere ajustes.

#### 1. Historia de usuario

   Título: Simplificar a Gestionar medicamentos.

   Rol: Precisar si farmacéuticos y administradores están autorizados para registrar y modificar medicamentos. Estos roles no aparecen definidos en el modelo verbal compartido de Poki Koa.

   Descripción: Evitar centrarse en el formulario interactivo. La necesidad principal es registrar y actualizar información de medicamentos.

   Beneficio: Es claro y pertinente, ya que busca mantener información confiable y prevenir errores.

   Alcance: Se pueden mantener registro y modificación en una misma HU, siempre que ambos procesos sean verificables.
#### 2. Criterios de aceptación

| CA | Observación para aplicar |
| --- | --- |
| CA1 | Especificar los campos obligatorios y el resultado esperado de un registro exitoso. |
| CA2 | Verificar que los datos se precarguen y que las modificaciones se almacenen correctamente. |
| CA3 | Definir las reglas exactas de validación. Aclarar si el stock admite cero y qué unidades corresponden a las dosis. |
| CA4 | Mantener el criterio, pero especificar que los mensajes indiquen claramente el error y cómo corregirlo. |
| CA5 | Mantener el criterio y definir cuándo se habilita nuevamente el botón. |

#### 3. Criterios faltantes

Se recomienda incorporar escenarios para:

- Registro exitoso y confirmación al usuario.

- Modificación exitosa de un medicamento.

- Prevención de medicamentos duplicados, si corresponde a las reglas del catálogo.

- Rechazo de dosis inválidas y cantidades de stock negativas.

- Manejo de errores cuando no se puede guardar la información.

- Restricción de registro y modificación según los permisos autorizados.

Los criterios deben describir comportamientos verificables mediante Dado – Cuando – Entonces, evitando expresiones como «Se implementó» o «Se adaptó».
#### 4. Coherencia con Poki Koa

El modelo verbal confirma que el sistema gestiona esquemas de medicación y permite consultar medicamentos administrados. Sin embargo, no especifica todavía la administración del catálogo, el control de stock ni los roles farmacéutico y administrador.

Por tanto, es necesario confirmar que estas funcionalidades forman parte del alcance de Poki Koa antes de aprobar la historia.
Resultado final

US-02: Pendiente de ajustes.

Prioridad de corrección: Validar la coherencia con el modelo verbal, precisar los roles autorizados, definir las reglas de validación y completar los escenarios de registro y modificación.

La historia tiene una base adecuada, pero requiere mayor precisión funcional para considerarse lista para desarrollo y pruebas.

### Usuario

#### US-03 — Issue [#16](https://github.com/Asulx/poki-koa-web/issues/16)
Desarrollo del listado de medicamentos
Última actualización del issue: 2026-09-02T20:44:13Z.
#### Descripcion Historia
Como usuario del sistema (personal de farmacia o médico), quiero visualizar un listado estructurado de todos los medicamentos registrados para consultar rápidamente el catálogo, verificar el stock disponible y acceder a sus opciones de edición.
Criterios de aceptación
- Se implementó una vista principal con una tabla (Data Grid) o listado de tarjetas para mostrar los medicamentos.
 La tabla incluye las columnas con la información clave (ej. Nombre, Principio activo, Dosis, Stock actual).
 Los datos se consumen de manera dinámica utilizando el Servicio de medicamentos (desarrollado en el Issue [#21](https://github.com/Asulx/poki-koa-web/issues/21)).
- Se implementó paginación o scroll infinito para evitar la sobrecarga de la interfaz al mostrar muchos registros.
 Cada registro de la lista cuenta con un botón de acciones (ej. un ícono de "Editar") que redirige al formulario de modificación (Issue [#17](https://github.com/Asulx/poki-koa-web/issues/17)).
- Se implementó un estado de carga (loading spinner o skeleton) que se muestra mientras se obtienen los datos del servidor.hacer el listado de medicamentos
…

### Clarita

#### Revisión US-03 — Issue [#16](https://github.com/Asulx/poki-koa-web/issues/16): Listado de medicamentos

Estado: Requiere ajustes menores.

#### 1. Historia de usuario

   Título: Simplificar a Listar medicamentos.

   Rol: Precisar los permisos del personal de farmacia y médico, especialmente respecto a la edición de medicamentos.

   Descripción: La necesidad y el beneficio son claros. Sin embargo, conviene separar la consulta del catálogo de los detalles sobre cómo se presenta la información.

   Alcance: Mantener el listado, la consulta de stock y el acceso a edición dentro de la misma historia, siempre que estén contemplados en los permisos del usuario.
#### 2. Criterios de aceptación

| CA | Observación para aplicar |
| --- | --- |
| CA1 | Evitar especificar componentes técnicos como Data Grid. Enfocarse en que el usuario pueda visualizar el listado. |
| CA2 | Especificar qué información debe mostrarse obligatoriamente por medicamento. |
| CA3 | Retirar la referencia técnica al servicio y al Issue [#21](https://github.com/Asulx/poki-koa-web/issues/21) del criterio funcional. Documentarla como dependencia técnica. |
| CA4 | Definir un comportamiento concreto de paginación o desplazamiento, evitando dejar dos alternativas abiertas. |
| CA5 | Verificar que la opción de edición aparezca únicamente para usuarios autorizados y permita acceder al medicamento seleccionado. |
| CA6 | Mantener el estado de carga, pero describir el comportamiento esperado sin imponer un componente visual específico. |

#### 3. Criterios faltantes

Se recomienda incorporar escenarios para:

- Listado vacío: informar cuando no existan medicamentos registrados.

- Error de consulta: mostrar un mensaje cuando no sea posible obtener los medicamentos.

- Stock disponible: asegurar que la cantidad mostrada corresponda a la información actualizada del catálogo.

- Permisos: permitir la consulta según los roles autorizados y restringir la edición cuando corresponda.

Redactar los criterios utilizando Dado – Cuando – Entonces, describiendo resultados verificables en lugar de tareas de implementación.
#### 4. Coherencia con Poki Koa

La consulta de medicamentos es coherente con el sistema. Sin embargo, el modelo verbal compartido todavía no define explícitamente un catálogo general de medicamentos, la gestión de inventario ni los permisos del personal de farmacia.

Es importante confirmar estos aspectos para asegurar la consistencia entre US-02 y US-03.
Resultado final

US-03: Pendiente de ajustes menores.

Prioridad de corrección: Eliminar detalles técnicos de los criterios funcionales, definir los permisos de edición y agregar escenarios de listado vacío y errores de consulta.

La historia está bien orientada y presenta criterios relevantes. Con estos ajustes podrá ser más clara, verificable y consistente con las demás historias de medicamentos.

### Usuario

#### US-04 — Issue [#13](https://github.com/Asulx/poki-koa-web/issues/13)
Desarrollar vista del listado de pacientes
Última actualización del issue: 2026-09-02T21:04:55Z.
Descripcion Historia
Como usuario del sistema (médico o personal administrativo) quiero visualizar un listado estructurado de todos los pacientes registrados
para consultar rápidamente su información resumida y acceder de forma ágil a sus perfiles completos.
Criterios de aceptación
- Se implementó la vista principal conteniendo una Tabla principal (Data Grid) para listar a los pacientes.
 La tabla despliega la información resumida y más relevante de cada paciente (ej. Nombre, RUT/Identificación, Edad o Fecha de nacimiento, y Teléfono).
 Los datos mostrados en la tabla se obtienen de forma dinámica consumiendo el Servicio de pacientes (desarrollado en el Issue [#21](https://github.com/Asulx/poki-koa-web/issues/21)).
- Se implementó un sistema de paginación en la tabla para manejar eficientemente grandes cantidades de registros.
 Cada fila incluye un botón o menú de acciones (ej. "Ver detalles" o "Editar") que conecta con el formulario de pacientes (Issue [#15](https://github.com/Asulx/poki-koa-web/issues/15)).
 La interfaz muestra un indicador de carga (loading state) mientras el sistema recupera la información del servidor.
…

### Clarita

#### Revisión US-04 — Issue [#13](https://github.com/Asulx/poki-koa-web/issues/13): Listado de pacientes

Estado: Requiere ajustes menores.

#### 1. Historia de usuario

   Título: Simplificar a Listar pacientes.

   Rol: Reemplazar el rol genérico por neonatólogos y matronas, de acuerdo con los roles médicos definidos anteriormente.

   Descripción: La necesidad y el beneficio son claros. Se recomienda mantener el enfoque en consultar pacientes y acceder a su información clínica.

   Alcance: Aclarar si cada profesional puede visualizar todos los pacientes o únicamente aquellos bajo su responsabilidad.
#### 2. Criterios de aceptación

| CA | Observación para aplicar |
| --- | --- |
| CA1 | Evitar términos técnicos como Data Grid. Enfocarse en la visualización del listado de pacientes. |
| CA2 | Corregir los campos mostrados. RUT y teléfono no corresponden a los datos principales definidos para los recién nacidos. Considerar ID único, nombre, sexo, edad gestacional, peso y fecha de ingreso. |
| CA3 | Retirar la referencia al servicio y al Issue [#21](https://github.com/Asulx/poki-koa-web/issues/21) del criterio funcional. Mantenerla como dependencia técnica. |
| CA4 | Especificar el comportamiento de la paginación, incluyendo cómo navegar entre páginas. |
| CA5 | Diferenciar las acciones de consultar detalles y editar. La edición debe respetar los permisos establecidos en US-01. |
| CA6 | Mantener el estado de carga, describiendo el comportamiento esperado sin imponer una implementación visual específica. |

#### 3. Criterios faltantes

Se recomienda incorporar escenarios para:

- Listado vacío: informar cuando no existan pacientes registrados.

- Error de consulta: mostrar un mensaje cuando no sea posible recuperar los pacientes.

- Acceso al perfil: verificar que al seleccionar un paciente se visualice su información correspondiente.

- Permisos: restringir el acceso a información clínica según los roles autorizados.

- Estado de internación: definir si el listado incluye pacientes egresados o únicamente pacientes actualmente hospitalizados.

Los criterios deben redactarse mediante Dado – Cuando – Entonces, describiendo resultados observables en lugar de tareas técnicas.
#### 4. Coherencia con Poki Koa

La historia está alineada con la necesidad de consultar información de los recién nacidos de la UCI Neonatal.

Sin embargo, presenta dos inconsistencias con el modelo verbal:

- Información demográfica: utiliza campos genéricos de pacientes en lugar de los datos neonatales definidos.

- Roles: incluye personal administrativo, mientras que anteriormente se estableció que neonatólogos y matronas son los responsables de la gestión de pacientes.

Además, conviene asegurar que el acceso al perfil permita consultar la información clínica, los signos vitales y las alertas correspondientes, según el alcance de Poki Koa.
Resultado final

US-04: Pendiente de ajustes menores.

Prioridad de corrección: Adaptar los campos al contexto neonatal, precisar los permisos de consulta, eliminar detalles técnicos de los criterios y contemplar los escenarios de listado vacío y errores de consulta.

La historia tiene una estructura adecuada y un objetivo funcional claro. Con estos ajustes será más coherente con Poki Koa y verificable durante las pruebas.

### Usuario

#### US-05 — Issue [#14](https://github.com/Asulx/poki-koa-web/issues/14)
Implementación de búsqueda y filtros de pacientes
Última actualización del issue: 2026-09-02T19:07:04Z.
Historia
Como usuario del sistema (médico o administrador) quiero poder buscar pacientes específicos por su nombre y aplicar filtros
para encontrar rápidamente sus registros o historiales sin tener que navegar manualmente por listas extensas.
Criterios de aceptación
- Se implementó una barra de búsqueda por nombre o identificador, optimizada para no sobrecargar el servidor (ej. usando debounce o buscando al presionar Enter).
- Se desarrollaron controles para los filtros avanzados (ej. por estado del paciente, fecha de ingreso, rango de edad, etc.).
 El sistema permite utilizar la búsqueda por texto y los filtros avanzados de manera simultánea.
- Se incluyó una opción visible y rápida para limpiar todos los filtros activos y restaurar la vista original.
 La interfaz muestra un mensaje claro y amigable (estado vacío o Empty State) cuando la búsqueda no arroja ningún resultado.

### Clarita

#### Revisión US-05 — Issue [#14](https://github.com/Asulx/poki-koa-web/issues/14): Búsqueda y filtros de pacientes

Estado: Requiere ajustes menores.

#### 1. Historia de usuario

   Título: Simplificar a Buscar pacientes. Si los filtros representan una funcionalidad importante, también es válido Buscar y filtrar pacientes.

   Rol: Reemplazar el rol genérico por neonatólogos y matronas, según los permisos definidos anteriormente.

   Descripción: La necesidad y el beneficio son claros. La historia está orientada a facilitar la localización de pacientes.

   Alcance: Mantener búsqueda y filtros en una sola historia, ya que ambas funcionalidades persiguen el mismo objetivo.
#### 2. Criterios de aceptación

| CA | Observación para aplicar |
| --- | --- |
| CA1 | Mantener la búsqueda por nombre e identificador. Retirar términos técnicos como debounce y definir cuándo se ejecuta la búsqueda. |
| CA2 | Especificar los filtros disponibles. Priorizar estado de internación, fecha de ingreso y edad gestacional, según el modelo neonatal. |
| CA3 | Es adecuado y verificable. Precisar que los resultados deben cumplir simultáneamente las condiciones seleccionadas. |
| CA4 | Es claro. Verificar que al limpiar los filtros se restablezca el listado completo de pacientes autorizados. |
| CA5 | Es adecuado. Mantener el mensaje cuando no existan coincidencias, evitando términos técnicos como Empty State. |

#### 3. Criterios faltantes

Se recomienda incorporar escenarios para:

- Búsqueda exitosa: mostrar únicamente los pacientes que coincidan con el nombre o identificador ingresado.

- Búsqueda parcial: definir si se permiten coincidencias por fragmentos del nombre.

- Filtros combinados: comprobar que se apliquen correctamente varias condiciones.

- Sin resultados: distinguir entre una búsqueda sin coincidencias y un error del sistema.

- Error de consulta: informar cuando no sea posible recuperar los resultados.

- Permisos: mostrar únicamente pacientes a los que el profesional tenga autorización de acceso.

Los criterios deben expresarse mediante Dado – Cuando – Entonces, priorizando resultados observables.
#### 4. Coherencia con Poki Koa

La historia está alineada con la consulta de pacientes de la UCI Neonatal.

Sin embargo, requiere considerar:

- Identificación: utilizar el identificador único del recién nacido definido en Poki Koa.

- Filtros clínicos: adaptar los filtros a los datos neonatales disponibles, evitando categorías genéricas que no estén contempladas.

- Roles: respetar los permisos de neonatólogos y matronas.

- Dependencia funcional: asegurar que la búsqueda y los filtros funcionen sobre el listado de pacientes definido en la US-04.

Resultado final

US-05: Pendiente de ajustes menores.

Prioridad de corrección: Precisar los filtros disponibles, adaptar los roles al modelo verbal, eliminar detalles técnicos y completar los escenarios de búsqueda y errores.

La historia tiene un objetivo claro y sus criterios cubren las funcionalidades principales. Con estos ajustes será más precisa, verificable y consistente con la US-04.

### Usuario

#### US-06 — Issue [#12](https://github.com/Asulx/poki-koa-web/issues/12)
 Implementar gráficos interactivos y visualización de estadísticas
Última actualización del issue: 2026-09-02T21:37:55Z.
Descripcion Historia
Como usuario administrador o gerente, quiero visualizar la información clave a través de gráficos interactivos y resúmenes estadísticos
para comprender rápidamente el volumen de datos (ej. flujo de pacientes, stock crítico) y facilitar la toma de decisiones.
Criterios de aceptación
- Se seleccionó e instaló una librería de visualización de datos compatible con el proyecto (ej. Chart.js, Recharts, ApexCharts).
- Se desarrollaron componentes de estadísticas resumidas (ej. tarjetas con números totales de pacientes registrados o medicamentos en bajo stock).
- Se implementaron gráficos interactivos (ej. de barras, líneas o anillo) que permiten al usuario ver detalles exactos al pasar el cursor (hover o tooltips).
 Los gráficos se alimentan con datos dinámicos obtenidos desde el backend (conectado al Servicio de reportes).
 La visualización es completamente responsiva, ajustando el tamaño de los gráficos para que sean legibles tanto en monitores grandes como en dispositivos móviles.
…

### Clarita

#### Revisión US-06 — Issue [#12](https://github.com/Asulx/poki-koa-web/issues/12): Gráficos y estadísticas

Estado: Requiere ajustes.

#### 1. Historia de usuario

   Título: Simplificar a Visualizar estadísticas.

   Rol: Precisar si administradores y gerentes existen como roles autorizados en Poki Koa, ya que no aparecen en el modelo verbal compartido.

   Descripción: La necesidad y el beneficio son claros. Se recomienda enfocarse en consultar indicadores para apoyar decisiones, evitando imponer una solución visual específica.

   Alcance: Definir qué indicadores estadísticos estarán disponibles para evitar una historia demasiado amplia.
#### 2. Criterios de aceptación

| CA | Observación para aplicar |
| --- | --- |
| CA1 | Eliminarlo como criterio funcional. La instalación de librerías es una tarea técnica, no un comportamiento verificable por el usuario. |
| CA2 | Definir exactamente qué indicadores se mostrarán y cómo se calcularán. |
| CA3 | Especificar qué información debe visualizar el usuario al interactuar con los gráficos, sin imponer tipos de gráficos o tecnologías. |
| CA4 | Retirar la referencia técnica al backend y al servicio de reportes. Verificar que las estadísticas reflejen los datos registrados en el sistema. |
| CA5 | Mantener la adaptación a diferentes pantallas, definiendo que los gráficos y sus valores permanezcan legibles. |

#### 3. Criterios faltantes

Se recomienda incorporar escenarios para:

- Carga exitosa: visualizar correctamente los indicadores y gráficos disponibles.

- Datos actualizados: asegurar que las estadísticas correspondan a la información vigente.

- Ausencia de datos: informar cuando no existan registros suficientes para generar estadísticas.

- Error de consulta: mostrar un mensaje cuando no sea posible recuperar la información.

- Permisos: restringir el acceso a estadísticas según los roles autorizados.

- Período de consulta: definir si las estadísticas corresponden a un período fijo o permiten seleccionar fechas.

Los criterios deben redactarse utilizando Dado – Cuando – Entonces y expresar resultados comprobables.
#### 4. Coherencia con Poki Koa

La visualización de estadísticas puede complementar las funcionalidades de gestión neonatal. Sin embargo, el modelo verbal compartido todavía no contempla explícitamente un módulo de reportes o indicadores administrativos.

Es necesario precisar:

- Indicadores de pacientes: por ejemplo, cantidad de recién nacidos hospitalizados, ingresos y egresos.

- Indicadores de medicamentos: confirmar si el control de stock forma parte del sistema, ya que no está definido en el modelo verbal.

- Roles: establecer quién puede consultar estadísticas generales y clínicas.

- Origen de los datos: asegurar que los indicadores correspondan a información efectivamente gestionada por Poki Koa.

Resultado final

US-06: Pendiente de ajustes.

Prioridad de corrección: Definir los indicadores estadísticos y sus reglas de cálculo, confirmar los roles autorizados, eliminar tareas técnicas de los criterios y contemplar escenarios sin datos y errores de consulta.

La historia tiene un beneficio claro, pero requiere mayor definición funcional para que sus criterios sean verificables y coherentes con el alcance de Poki Koa.

### Usuario

#### US-06 — Issue [#12](https://github.com/Asulx/poki-koa-web/issues/12)
 Implementar gráficos interactivos y visualización de estadísticas
Última actualización del issue: 2026-09-02T21:37:55Z.
Descripcion Historia
Como usuario administrador o gerente, quiero visualizar la información clave a través de gráficos interactivos y resúmenes estadísticos
para comprender rápidamente el volumen de datos (ej. flujo de pacientes, stock crítico) y facilitar la toma de decisiones.
Criterios de aceptación
- Se seleccionó e instaló una librería de visualización de datos compatible con el proyecto (ej. Chart.js, Recharts, ApexCharts).
- Se desarrollaron componentes de estadísticas resumidas (ej. tarjetas con números totales de pacientes registrados o medicamentos en bajo stock).
- Se implementaron gráficos interactivos (ej. de barras, líneas o anillo) que permiten al usuario ver detalles exactos al pasar el cursor (hover o tooltips).
 Los gráficos se alimentan con datos dinámicos obtenidos desde el backend (conectado al Servicio de reportes).
 La visualización es completamente responsiva, ajustando el tamaño de los gráficos para que sean legibles tanto en monitores grandes como en dispositivos móviles.

### Usuario

#### US-07 — Issue [#18](https://github.com/Asulx/poki-koa-web/issues/18)
Desarrollar la vista y lógica del módulo de reportes
Última actualización del issue: 2026-10-03T19:26:34Z.
Descripcion Historia
Como usuario administrador o coordinador, quiero acceder a un módulo centralizado de reportes en la plataforma
para visualizar las métricas clave, analizar datos del sistema y tomar decisiones informadas.
Criterios de aceptación
- Se creó la vista principal del módulo de reportes y se agregó su respectivo enlace en la barra de navegación lateral.
 La interfaz integra y muestra correctamente los datos consumidos desde el Servicio de reportes (desarrollado en el Issue [#21](https://github.com/Asulx/poki-koa-web/issues/21)).
- Se implementaron componentes visuales (tablas de resumen o gráficos básicos) para presentar la información de forma clara.
- Se integraron los botones y la lógica de la exportación a PDF y Excel (desarrollada en el Issue [#19](https://github.com/Asulx/poki-koa-web/issues/19)) dentro de esta vista.
 La vista maneja correctamente los estados de carga (loading) y muestra un mensaje amigable si no hay datos disponibles para reportar.
…

### Clarita

#### Revisión US-06 — Issue [#12](https://github.com/Asulx/poki-koa-web/issues/12): Visualizar estadísticas

Estado: Requiere ajustes.

La US-06 se mantiene con las observaciones anteriores. Al incorporar la US-07, aparece una consideración adicional: ambas historias presentan un posible solapamiento funcional.

La US-06 debería concentrarse en la visualización de indicadores y gráficos, mientras que la US-07 debería centrarse en el acceso y las funcionalidades del módulo de reportes.

### Clarita

#### Revisión US-07 — Issue [#18](https://github.com/Asulx/poki-koa-web/issues/18): Módulo de reportes

Estado: Requiere ajustes.

#### 1. Historia de usuario

   Título: Simplificar a Consultar reportes.

   Rol: Precisar si administradores y coordinadores son roles autorizados en Poki Koa. Estos roles no aparecen definidos en el modelo verbal compartido.

   Descripción: La necesidad y el beneficio son claros. Sin embargo, conviene especificar qué información necesitan consultar los usuarios.

   Alcance: Evitar duplicar la visualización de estadísticas y gráficos de la US-06. La US-07 debe concentrarse en la consulta y gestión de reportes.
#### 2. Criterios de aceptación

| CA | Observación para aplicar |
| --- | --- |
| CA1 | Mantener el acceso al módulo, pero describir que el usuario autorizado pueda ingresar desde la navegación principal. |
| CA2 | Retirar las referencias técnicas al servicio y al Issue [#21](https://github.com/Asulx/poki-koa-web/issues/21). Especificar qué información debe mostrar el módulo. |
| CA3 | Revisar posible duplicidad con US-06. Los gráficos y estadísticas deberían definirse principalmente en esa historia. |
| CA4 | Mantener las opciones de exportación, pero verificar que permitan descargar correctamente los reportes en PDF y Excel. Evitar duplicar los criterios de la US correspondiente al Issue [#19](https://github.com/Asulx/poki-koa-web/issues/19). |
| CA5 | Es adecuado. Complementar con el comportamiento esperado cuando ocurre un error al recuperar los datos. |

#### 3. Criterios faltantes

Se recomienda incorporar escenarios para:

- Acceso autorizado: permitir ingresar al módulo únicamente a los roles correspondientes.

- Consulta exitosa: mostrar los reportes disponibles con información correcta.

- Selección de reportes: definir si existen distintos tipos de reportes y cómo se seleccionan.

- Ausencia de datos: informar cuando no existan registros para generar un reporte.

- Error de consulta: mostrar un mensaje cuando falle la recuperación de información.

- Exportación: verificar que los archivos descargados correspondan a los datos del reporte consultado.

Los criterios deben utilizar Dado – Cuando – Entonces, describiendo resultados verificables y no tareas de desarrollo.
#### 4. Relación entre US-06 y US-07

| Aspecto | US-06 | US-07 |
| --- | --- | --- |
| Objetivo principal | Visualizar estadísticas | Consultar reportes |
| Funcionalidad | Indicadores y gráficos interactivos | Acceso, consulta y exportación |
| Información | Métricas resumidas | Reportes definidos por el sistema |
| Dependencias | Datos para calcular indicadores | US-06, si incorpora sus gráficos, e Issue [#19](https://github.com/Asulx/poki-koa-web/issues/19) para exportación |
| Riesgo | Duplicación de gráficos | Duplicación de visualizaciones y criterios |

Recomendación: Mantener ambas historias independientes, pero delimitar sus responsabilidades. La US-07 puede integrar los gráficos de la US-06 sin volver a exigir su implementación.
#### 5. Coherencia con Poki Koa

El modelo verbal compartido contempla información clínica, pacientes, medicamentos, signos vitales y alertas. Sin embargo, no define explícitamente un módulo de reportes.

Por ello, se recomienda:

- Determinar qué reportes se generarán a partir de los datos neonatales.

- Confirmar los roles autorizados para consultar información clínica y administrativa.

- Definir si los reportes tendrán filtros por fechas, pacientes o estados de internación.

- Asegurar que la información exportada respete los permisos de acceso.

Resultado final

US-06 — Visualizar estadísticas
Requiere ajustes

US-07 — Consultar reportes
Requiere ajustes

Prioridad de corrección: Resolver el solapamiento entre ambas historias, definir qué indicadores y reportes estarán disponibles, precisar los roles autorizados y transformar los criterios técnicos en comportamientos verificables.

Ambas historias pueden mantenerse separadas, siempre que la US-06 se enfoque en las estadísticas y la US-07 en la consulta y gestión de reportes.

### Usuario

El ultimo mensaje fue una issue repetida sin querer, aqui va la 7: US-07 — Issue [#18](https://github.com/Asulx/poki-koa-web/issues/18)
Desarrollar la vista y lógica del módulo de reportes
Última actualización del issue: 2026-10-03T19:26:34Z.
Descripcion Historia
Como usuario administrador o coordinador, quiero acceder a un módulo centralizado de reportes en la plataforma
para visualizar las métricas clave, analizar datos del sistema y tomar decisiones informadas.
Criterios de aceptación
- Se creó la vista principal del módulo de reportes y se agregó su respectivo enlace en la barra de navegación lateral.
 La interfaz integra y muestra correctamente los datos consumidos desde el Servicio de reportes (desarrollado en el Issue [#21](https://github.com/Asulx/poki-koa-web/issues/21)).
- Se implementaron componentes visuales (tablas de resumen o gráficos básicos) para presentar la información de forma clara.
- Se integraron los botones y la lógica de la exportación a PDF y Excel (desarrollada en el Issue [#19](https://github.com/Asulx/poki-koa-web/issues/19)) dentro de esta vista.
 La vista maneja correctamente los estados de carga (loading) y muestra un mensaje amigable si no hay datos disponibles para reportar.

### Clarita

#### Revisión US-07 — Issue [#18](https://github.com/Asulx/poki-koa-web/issues/18): Módulo de reportes

Estado: Requiere ajustes.

#### 1. Historia de usuario

   Título: Simplificar a Consultar reportes.

   Rol: Precisar los permisos de administradores y coordinadores, ya que no están definidos en el modelo verbal compartido de Poki Koa.

   Descripción: La necesidad y el beneficio son claros, pero falta especificar qué reportes necesita consultar el usuario.

   Alcance: Diferenciar esta historia de la US-06, que ya contempla gráficos y estadísticas, para evitar funcionalidades duplicadas.
#### 2. Criterios de aceptación

| CA | Observación para aplicar |
| --- | --- |
| CA1 | Es adecuado. Enfocarlo en que el usuario autorizado pueda acceder al módulo desde la navegación principal. |
| CA2 | Retirar las referencias técnicas al servicio y al Issue [#21](https://github.com/Asulx/poki-koa-web/issues/21). Definir qué información debe presentar el módulo. |
| CA3 | Revisar la duplicidad con US-06. Evitar volver a exigir gráficos y estadísticas ya contemplados en esa historia. |
| CA4 | Mantener el acceso a la exportación, pero dejar la generación y descarga de archivos como responsabilidad del Issue [#19](https://github.com/Asulx/poki-koa-web/issues/19). |
| CA5 | Es adecuado. Complementar con el comportamiento esperado cuando falla la consulta de información. |

#### 3. Criterios faltantes

Se recomienda incorporar escenarios para:

- Acceso autorizado: restringir la consulta a los roles correspondientes.

- Consulta exitosa: mostrar correctamente los reportes disponibles.

- Selección de reportes: definir qué tipos de reportes se pueden consultar.

- Sin información: informar cuando no existan datos disponibles.

- Error de consulta: notificar cuando no sea posible recuperar los reportes.

- Exportación: comprobar que el reporte seleccionado pueda enviarse a la funcionalidad de exportación correspondiente.

Los criterios deben redactarse mediante Dado – Cuando – Entonces, describiendo resultados observables y verificables.
#### 4. Coherencia con Poki Koa

La historia puede complementar el sistema de gestión neonatal, pero el modelo verbal compartido no define explícitamente el módulo de reportes.

Se recomienda precisar qué información podrá consultarse, por ejemplo, ingresos y egresos de pacientes, ocupación de cunas o administración de medicamentos, siempre que estos indicadores estén contemplados en el alcance del proyecto.

También es importante establecer los permisos para consultar información clínica sensible.
Resultado final

US-07: Pendiente de ajustes.

Prioridad de corrección: Definir los tipos de reportes, precisar los roles autorizados, evitar duplicidad con US-06 y separar los criterios funcionales de las dependencias técnicas.

La historia tiene un objetivo claro, pero necesita delimitar mejor su alcance para garantizar que sea verificable y consistente con las demás funcionalidades de Poki Koa.

### Clarita

#### Revisión US-08 — Issue [#19](https://github.com/Asulx/poki-koa-web/issues/19): Exportación de reportes
Estado: Requiere ajustes menores.

#### 1. Historia de usuario

- Título: Simplificar a Exportar reportes.
- Rol: Reemplazar "usuario del sistema" por los roles autorizados para consultar y exportar reportes, manteniendo coherencia con la US-07.
- Descripción: La necesidad y el beneficio son claros. Compartir, imprimir y analizar información son objetivos válidos.
- Alcance: Mantener PDF y Excel en una sola historia, ya que ambos formatos cumplen el mismo objetivo funcional.

#### 2. Criterios de aceptación

| CA | Observación para aplicar |
| --- | --- |
| CA1 | Es adecuado. Precisar qué información debe incluir el PDF y verificar que conserve su legibilidad. |
| CA2 | Definir el formato requerido. No dejar Excel o CSV como alternativas abiertas. Si se requieren ambos, deben establecerse explícitamente. |
| CA3 | Es claro y verificable. Definir una convención consistente para los nombres de archivos, incluyendo tipo de reporte y fecha. |
| CA4 | Es adecuado. Especificar que el botón vuelva a habilitarse al finalizar la descarga o cuando ocurra un error. |
#### 3. Criterios faltantes
   Se recomienda incorporar escenarios para:

- Exportación exitosa: comprobar que el archivo se genere y descargue correctamente.
- Integridad de datos: verificar que la información exportada coincida con el reporte consultado.
- Filtros aplicados: definir si se exportan todos los registros o únicamente los resultados filtrados.
- Sin información: establecer qué sucede cuando se intenta exportar un reporte sin datos.
- Error de exportación: mostrar un mensaje cuando falle la generación o descarga del archivo.
- Permisos: impedir que usuarios no autorizados exporten información.
  Los criterios deben redactarse mediante Dado – Cuando – Entonces, describiendo resultados verificables y evitando expresiones como «Se implementó».

#### 4. Coherencia con Poki Koa
   La historia complementa directamente la US-07 — Consultar reportes.
   Sin embargo, deben considerarse tres aspectos:

- Confidencialidad: los reportes pueden contener información clínica sensible de recién nacidos. La exportación debe respetar los permisos de acceso.
- Contenido: definir qué información neonatal puede incluirse en los archivos exportados.
- Dependencia funcional: la US-08 debe encargarse de generar y descargar los archivos, mientras que la US-07 proporciona el acceso a la funcionalidad.
  Resultado final
  US-08: Pendiente de ajustes menores.
  Prioridad de corrección: Precisar los roles autorizados, definir los formatos de exportación, garantizar la integridad de los datos y agregar escenarios de error y ausencia de información.
  La historia presenta un objetivo claro y criterios relevantes. Con estos ajustes será verificable y consistente con el módulo de reportes de Poki Koa.

### Usuario

#### US-09 — Issue [#39](https://github.com/Asulx/poki-koa-web/issues/39)
Gestión y modificación de turnos por el Administrador
Última actualización del issue: 2026-09-07T12:49:44Z.
Historia de Usuario
Como administrador de la plataforma,
quiero poder agregar y eliminar personal médico (doctores y enfermeros) en los distintos turnos (Mañana, Tarde, Noche),
para mantener la cobertura adecuada en el área y gestionar rápidamente las ausencias o cambios imprevistos.
Criterios de Aceptación
 Control de Acceso. Solo los usuarios autenticados con el rol de Administrador deben visualizar los controles de edición (+ Agregar, ✕ para eliminar y los botones de Activar turno) en el panel de gestión.
 Agregar Personal. Al hacer clic en el botón + Agregar dentro de una tarjeta de turno (ej. Mañana 07:00–15:00), se debe desplegar un selector o modal que muestre únicamente al personal disponible que no esté ya asignado a ese bloque.
 Remover Personal. Al hacer clic en el ícono ✕ junto al identificador de un profesional (ej. DM Dra. María López), el sistema debe mostrar un breve cuadro de confirmación antes de desvincularlo del turno para evitar eliminaciones accidentales.
 Actualización Dinámica de la UI. Al confirmar la adición o eliminación de un miembro del personal, el contador de la cabecera del turno (ej. PERSONAL (3)) y la lista visible deben actualizarse en tiempo real sin necesidad de recargar la página.
 Validación de Superposición. El sistema debe bloquear o mostrar una alerta si se intenta asignar a un mismo profesional a dos turnos consecutivos que excedan el límite de horas permitidas, o al mismo turno dos veces.
Tareas Técnicas sugeridas
-[ ] Implementar validación del rol de usuario para renderizar condicionalmente los botones de acción en el componente de la tarjeta de turno.
-[ ] Crear el modal/dropdown para consultar y seleccionar al personal disponible desde la base de datos.
-[ ] Integrar los endpoints de actualización (POST/DELETE) para modificar la asignación del personal en el backend.
-[ ] Manejar el estado global (ej. React Context, Redux o Zustand) para reflejar los cambios en el contador y la lista de forma inmediata.

### Usuario

#### US-10 — Issue [#40](https://github.com/Asulx/poki-koa-web/issues/40)
Navegación interactiva desde Monitor de Cunas hacia Detalles del Bebé
Última actualización del issue: 2026-09-07T12:49:34Z.
Historia de Usuario
Como profesional de la salud (médico o enfermero),
quiero poder hacer clic en la tarjeta o indicador de un paciente específico dentro de la vista "Monitor de Cunas",
para acceder directamente a la pantalla de "Detalles del Bebé" y revisar su información clínica, signos vitales y plan de cuidados rápidamente.
Criterios de Aceptación
 Interacción de clic. Al hacer clic sobre cualquier área interactiva de la tarjeta de un bebé (o cuna) en la pantalla de "Monitor de Cunas", el sistema debe redirigir al usuario a la vista de "Detalles del Bebé".
 Carga dinámica de datos. La pantalla de "Detalles del Bebé" debe cargar automáticamente la información correspondiente al paciente seleccionado (ej. nombre, cuna, diagnóstico, signos vitales actuales) mediante su ID o identificador único.
 Indicador visual (UX). Al pasar el cursor sobre las tarjetas en el Monitor de Cunas, el cursor debe cambiar a modo "puntero" (mano) y la tarjeta debe tener un leve efecto visual (hover) para indicar que es un elemento en el que se puede hacer clic.
 Navegación de regreso. En la vista de "Detalles del Bebé", el botón de retroceso (← ubicado junto al título) debe estar funcional y devolver al usuario exactamente a la vista del "Monitor de Cunas" conservando el estado anterior.
 Actualización de la ruta (URL). La URL de la aplicación debe actualizarse para reflejar la vista del paciente específico (ejemplo: /monitor/cuna-01 o /detalles-bebe/ID123), permitiendo que el enlace pueda ser recargado o compartido sin perder la vista.
#### Tareas Técnicas sugeridas
-[ ] Envolver el componente de la tarjeta de la cuna en el "Monitor de Cunas" con el componente de enlace/navegación (ej.  de React Router o equivalente).
-[ ] Configurar las rutas en el frontend para aceptar parámetros dinámicos (ej. /:idPaciente).
-[ ] Implementar la función en "Detalles del Bebé" que extraiga el ID de la URL y realice la petición (fetch) al backend para obtener los datos específicos de ese paciente.
[ ] Configurar el botón ← usando la función de historial del enrutador (ej. navigate(-1) o router.back()).

### Clarita

#### Revisión US-09 — Issue [#39](https://github.com/Asulx/poki-koa-web/issues/39): Gestión de turnos
Estado: Requiere ajustes.

#### 1. Historia de usuario

- Título: Simplificar a Gestionar turnos.
- Rol: El administrador está claramente identificado, pero debe confirmarse que este rol tiene permisos para gestionar turnos en Poki Koa.
- Descripción: La necesidad y el beneficio son claros. Se identifica el valor de mantener una cobertura adecuada del personal médico.
- Alcance: Mantener la asignación y eliminación de personal en una sola historia. Sin embargo, la activación de turnos aparece en los criterios sin estar contemplada en la descripción.

#### 2. Criterios de aceptación

| CA | Observación para aplicar |
| --- | --- |
| CA1. Control de acceso | Es adecuado. Complementar verificando que usuarios no autorizados tampoco puedan modificar turnos mediante solicitudes directas al sistema. |
| CA2. Agregar personal | Es claro. Definir qué condiciones determinan que un profesional está disponible para un turno. |
| CA3. Remover personal | Es adecuado. Incorporar el comportamiento cuando el administrador cancela la confirmación. |
| CA4. Actualización dinámica | Es verificable. Asegurar que el contador y la lista reflejen únicamente cambios guardados correctamente. |
| CA5. Superposición | Requiere precisión. Definir el máximo de horas permitido y las reglas para turnos consecutivos o superpuestos. |
#### 3. Criterios faltantes
   Se recomienda incorporar escenarios para:

- Asignación exitosa: confirmar que el profesional quedó asignado al turno seleccionado.
- Eliminación exitosa: verificar que el profesional ya no figure en el turno.
- Turno sin personal disponible: informar cuando no existan profesionales que puedan asignarse.
- Error de actualización: mostrar un mensaje si no es posible guardar los cambios.
- Cobertura mínima: definir si el sistema debe advertir cuando la eliminación de un profesional deja un turno sin cobertura suficiente.
- Activación de turnos: aclarar su comportamiento o trasladarlo a otra historia.

#### 4. Coherencia con Poki Koa
   La gestión de turnos puede complementar el funcionamiento de la UCI Neonatal, pero no aparece definida en el modelo verbal compartido.
   También se debe unificar la denominación de los profesionales: el modelo identifica neonatólogos y matronas, mientras que esta historia menciona doctores y enfermeros.
   Las tareas técnicas están correctamente separadas de los criterios de aceptación. Deben mantenerse como actividades de implementación.
   Resultado final: US-09 — Pendiente de ajustes.
   Prioridad: Definir las reglas de disponibilidad, superposición y cobertura mínima; aclarar la activación de turnos y confirmar los roles autorizados.

### Clarita

#### Revisión US-10 — Issue [#40](https://github.com/Asulx/poki-koa-web/issues/40): Navegación hacia detalles del bebé
Estado: Requiere ajustes menores.

#### 1. Historia de usuario

- Título: Simplificar a Consultar detalles del bebé.
- Rol: Precisar los roles como neonatólogos y matronas, de acuerdo con el modelo verbal.
- Descripción: La necesidad y el beneficio son claros. La historia expresa correctamente el objetivo de acceder rápidamente a información clínica.
- Alcance: Mantener la navegación desde el Monitor de Cunas hacia el perfil del recién nacido, sin incluir la implementación completa de los datos clínicos.

#### 2. Criterios de aceptación

| CA | Observación para aplicar |
| --- | --- |
| CA1. Interacción de clic | Es adecuado. Precisar que la navegación debe dirigirse al paciente asociado a la cuna seleccionada. |
| CA2. Carga dinámica | Es claro. Verificar que se muestre la información del bebé correcto, utilizando su identificador único. |
| CA3. Indicador visual | Es adecuado como requisito de usabilidad. Considerar también la navegación mediante teclado y dispositivos táctiles. |
| CA4. Navegación de regreso | Es verificable. Precisar qué estado debe conservarse al regresar, por ejemplo filtros, selección o posición del listado. |
| CA5. Actualización de URL | Es adecuado. Definir una estructura de URL consistente y garantizar que el acceso directo respete los permisos del usuario. |
#### 3. Criterios faltantes
   Se recomienda incorporar escenarios para:

- Cuna sin paciente: definir qué sucede cuando se selecciona una cuna desocupada.
- Paciente no encontrado: mostrar un mensaje cuando el identificador no corresponda a un bebé registrado.
- Error de carga: informar cuando no sea posible recuperar la información clínica.
- Acceso no autorizado: impedir la visualización de datos clínicos por usuarios sin permisos.
- Acceso directo: verificar que al abrir o recargar el enlace se muestre el paciente correcto.
- Cambio de asignación: asegurar que la navegación considere la asociación vigente entre cuna y paciente.

#### 4. Coherencia con Poki Koa
   La historia está directamente alineada con el modelo verbal, ya que contempla:

- La asociación entre cada recién nacido y su cuna.
- La consulta de información clínica y diagnósticos.
- La visualización de signos vitales.
- El acceso al plan de cuidados.
  La principal consideración es distinguir la navegación hacia los detalles del bebé de la implementación de las funcionalidades clínicas que aparecen en esa pantalla.
  Las tareas técnicas pueden mantenerse separadas como actividades de desarrollo.
  Resultado final: US-10 — Pendiente de ajustes menores.
  Prioridad: Definir el comportamiento de las cunas desocupadas, garantizar que se consulte el paciente correcto y contemplar errores de carga y permisos.

Resumen de ambas revisiones

| Historia | Estado | Principal observación |
| --- | --- | --- |
| US-09 — Gestionar turnos | Requiere ajustes | Faltan reglas de negocio sobre disponibilidad y cobertura. |
| US-10 — Consultar detalles del bebé | Ajustes menores | Faltan escenarios alternativos y validaciones de acceso. |
Recomendación general: En ambas historias, conservar el formato Dado – Cuando – Entonces para los criterios de aceptación y mantener los detalles de React, rutas, componentes y endpoints exclusivamente en las tareas técnicas.
La US-10 presenta mayor coherencia con el modelo verbal actual de Poki Koa. La US-09 necesita confirmar primero su alcance funcional dentro del sistema.
