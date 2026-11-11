# Resultados de pruebas — Entregable 2

## Ejecución del equipo en Bruno de escritorio

Versión: usebruno v4.2.1. Entorno: `Local`.
Servidor: `http://127.0.0.1:8000`.

| Resultado                       | Cantidad        |
| ------------------------------- | --------------- |
| Casos completos aprobados       | 44 (22 por API) |
| Solicitudes aprobadas           | 94 de 94        |
| Solicitudes fallidas u omitidas | 0               |
| Verificaciones aprobadas        | 265 de 265      |

Evidencia: [reporte HTML exportado por el equipo](../../qa/entrega2/resultado-bruno-equipo.html).
Colección: [archivos Bruno](../../qa/entrega2/bruno/).

## Resultados por caso

Cada resultado incluye la solicitud principal y sus verificaciones secundarias.

| Caso | Objetivo                                                     | HTTP esperado | HTTP observado | Caso completo |
| ---- | ------------------------------------------------------------ | ------------- | -------------- | ------------- |
| B01  | Registro válido con médico existente                       | 201           | 201            | PASS          |
| B02  | Identificador obligatorio ausente                            | 400           | 400            | PASS          |
| B03  | Identificador ya registrado                                  | 400           | 400            | PASS          |
| B04  | Nombre vacío                                                | 400           | 400            | PASS          |
| B05  | Nombre de 199 caracteres                                     | 201           | 201            | PASS          |
| B06  | Nombre de 200 caracteres                                     | 201           | 201            | PASS          |
| B07  | Nombre de 201 caracteres                                     | 400           | 400            | PASS          |
| B08  | Peso no numérico                                            | 400           | 400            | PASS          |
| B09  | Peso -0.01                                                   | 400           | 400            | PASS          |
| B10  | Peso 0                                                       | 400           | 400            | PASS          |
| B11  | Peso 0.01                                                    | 201           | 201            | PASS          |
| B12  | Peso y fecha opcionales nulos                                | 201           | 201            | PASS          |
| B13  | Fecha de nacimiento: ayer                                    | 201           | 201            | PASS          |
| B14  | Fecha de nacimiento: hoy                                     | 201           | 201            | PASS          |
| B15  | Fecha de nacimiento: mañana                                  | 400           | 400            | PASS          |
| B16  | Sexo fuera del catálogo                                     | 400           | 400            | PASS          |
| B17  | Médico inexistente                                          | 400           | 400            | PASS          |
| B18  | Modificar diagnóstico sin perder otros datos                | 200           | 200            | PASS          |
| B19  | Edición inválida no guarda ni siquiera los campos válidos | 400           | 400            | PASS          |
| B20  | Consultar paciente inexistente                               | 404           | 404            | PASS          |
| B21  | Recuperar datos para edición y relaciones                   | 200           | 200            | PASS          |
| B22  | Eliminar paciente libera cuna y elimina medicación asociada | 204           | 204            | PASS          |
| M01  | Registro válido en catálogo                                | 201           | 201            | PASS          |
| M02  | Nombre obligatorio                                           | 400           | 400            | PASS          |
| M03  | Principio activo vacío                                      | 400           | 400            | PASS          |
| M04  | Nombre de 150 caracteres                                     | 201           | 201            | PASS          |
| M05  | Nombre de 151 caracteres                                     | 400           | 400            | PASS          |
| M06  | Principio activo de 150 caracteres                           | 201           | 201            | PASS          |
| M07  | Principio activo de 151 caracteres                           | 400           | 400            | PASS          |
| M08  | Dosis no numérica                                           | 400           | 400            | PASS          |
| M09  | Dosis cero                                                   | 400           | 400            | PASS          |
| M10  | Dosis mínima 0.01 mg                                        | 201           | 201            | PASS          |
| M11  | Dosis con exceso de decimales                                | 400           | 400            | PASS          |
| M12  | Stock cero                                                   | 400           | 400            | PASS          |
| M13  | Stock mínimo una unidad                                     | 201           | 201            | PASS          |
| M14  | Stock fraccionario                                           | 400           | 400            | PASS          |
| M15  | Stock obligatorio                                            | 400           | 400            | PASS          |
| M16  | Dosis obligatoria                                            | 400           | 400            | PASS          |
| M17  | Consulta para precarga                                       | 200           | 200            | PASS          |
| M18  | Modificar stock y conservar otros campos                     | 200           | 200            | PASS          |
| M19  | Edición inválida no guarda cambios parciales               | 400           | 400            | PASS          |
| M20  | Producto inexistente                                         | 404           | 404            | PASS          |
| M21  | Modificar todos los campos                                   | 200           | 200            | PASS          |
| M22  | PUT incompleto conserva el producto                          | 400           | 400            | PASS          |

## Cambio de herramienta

Thunder Client 2.41.7 gratuito bloqueó las colecciones. El equipo utilizó Bruno
para ejecutar y exportar las pruebas. La sustitución y el procedimiento se
explican en [Uso de Bruno](USO_BRUNO.md).
