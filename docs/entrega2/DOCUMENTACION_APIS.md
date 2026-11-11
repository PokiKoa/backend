# Documentación de APIs — Entregable 2

## Alcance

Las APIs seleccionadas son gestión de pacientes (US-01, [issue #15](https://github.com/Asulx/poki-koa-web/issues/15)) y catálogo
de medicamentos (US-02, [issue #17](https://github.com/Asulx/poki-koa-web/issues/17)).
El catálogo incorpora nombre, principio activo, dosis en miligramos y cantidad
en stock. Es independiente de la medicación asignada a pacientes que sigue
expuesta en `/api/medicamentos/`.

La implementación corresponde al backend. El formulario, los mensajes visuales,
la validación en tiempo real y el estado del botón Guardar descritos en el issue
requieren frontend y no quedan acreditados por estas APIs. Tampoco hay control
de acceso por rol en estos endpoints; los roles descritos en la HU no están
implementados como permisos.

Las solicitudes con cuerpo utilizan JSON y la cabecera `Content-Type: application/json`.
La URL base local es `http://127.0.0.1:8000`.

## Pacientes — US-01

Base: `/api/bebes/`. POST registra; GET lista; GET, PATCH, PUT y DELETE
sobre `/api/bebes/{id}/` consultan, modifican y eliminan pacientes.

| Criterio backend | Comportamiento | Casos |
|---|---|---|
| B-CA1 | Alta válida: 201, ID y datos persistidos. | B01 |
| B-CA2 | Identificador único y obligatorio; nombre obligatorio hasta 200 caracteres; edad_meses entera y obligatoria; sexo F/M. | B02–B07, B16 |
| B-CA3 | Peso opcional, numérico y positivo; fecha de nacimiento opcional y no futura. | B08–B15, B19 |
| B-CA4 | El médico asignado debe existir. | B01, B17 |
| B-CA5 | Consulta y edición persistida, rechazo sin cambios parciales y 404 para recursos inexistentes. | B18–B21 |
| B-CA6 | Eliminación con cascada de medicación y liberación de cuna; comportamiento adicional del backend. | B22 |

La fecha de referencia de la validación de nacimiento es UTC.

Ejemplo de POST con datos ficticios y un médico previamente registrado:

```json
{
  "identificador": "BEB-EJEMPLO-01",
  "nombre_completo": "Paciente de ejemplo",
  "edad_meses": 0,
  "sexo": "F",
  "peso": 3.2,
  "medico_a_cargo": 910001
}
```

El alta válida responde 201 con el `id` generado y los datos del paciente.
GET `/api/bebes/{id}/` permite recuperarlos. PATCH modifica únicamente los campos
recibidos y responde 200; DELETE responde 204 sin cuerpo. Una validación inválida
responde 400 con errores por campo, y un ID inexistente responde 404.
Por ejemplo, un PATCH con `{"peso": 0}` se rechaza y conserva los datos anteriores.

## Catálogo de medicamentos — US-02

| Método y ruta | Resultado |
|---|---|
| POST `/api/catalogo-medicamentos/` | 201 con el producto creado; 400 si hay campos inválidos. |
| GET `/api/catalogo-medicamentos/` | 200 con la lista ordenada por ID. |
| GET `/api/catalogo-medicamentos/{id}/` | 200 con datos para precargar la edición; 404 si no existe. |
| PATCH `/api/catalogo-medicamentos/{id}/` | 200; modifica solo los campos enviados. |
| PUT `/api/catalogo-medicamentos/{id}/` | 200; requiere los cuatro campos editables. |

DELETE no está habilitado para el catálogo: el issue solicita registro y modificación.

| Campo | Regla |
|---|---|
| `id` | Generado por el servidor, solo lectura. |
| `nombre` | Texto obligatorio, no vacío, hasta 150 caracteres. |
| `principio_activo` | Texto obligatorio, no vacío, hasta 150 caracteres. |
| `dosis_mg` | Decimal obligatorio, entre 0.01 y 99999999.99, máximo dos decimales. La respuesta lo representa como cadena decimal. |
| `stock` | Entero obligatorio, entre 1 y 2147483647 unidades. |

Se adoptan dosis en mg y stock estrictamente positivo según el criterio del issue
que exige números positivos. Por tanto, stock cero se rechaza; representar productos
agotados requeriría acordar y cambiar esa regla. La precisión y los máximos indicados
son límites de almacenamiento, no límites clínicos. No hay descuento automático de
stock al administrar medicación, ni restricción de nombres duplicados: esas reglas
no están definidas en el issue.

Ejemplo de cuerpo para POST o PUT, con datos ficticios:

```json
{
  "nombre": "Producto QA",
  "principio_activo": "Sustancia QA",
  "dosis_mg": "1.00",
  "stock": 10
}
```

Un PATCH `{"stock": 5}` conserva nombre, principio activo y dosis. Un PATCH
`{"nombre": "Cambio", "stock": -1}` responde 400 con el error bajo la clave
`stock` y no guarda ninguno de los cambios. El texto de error puede depender
de la versión e idioma de Django; las pruebas verifican el campo y la persistencia.

| Criterio backend | Comportamiento | Casos |
|---|---|---|
| M-CA1 | Registrar un producto y devolver sus datos persistidos. | M01 y otras altas válidas |
| M-CA2 | Recuperar para edición, modificar y volver a consultar; rechazar actualizaciones inválidas sin cambios parciales. | M17–M22 |
| M-CA3 | Campos obligatorios, longitud, dosis decimal positiva y stock entero positivo; errores por campo. | M02–M16, M19, M22 |

Los identificadores B-CA y M-CA corresponden a la trazabilidad local con la matriz de pruebas.

## Persistencia y compatibilidad

`MedicamentoCatalogo` es una tabla nueva, creada por la migración
`0008_medicamentocatalogo`. No convierte ni elimina las asignaciones existentes.
Las restricciones SQL impiden dosis no positivas y stock fuera del rango permitido.
El serializador valida además los campos obligatorios, longitudes y precisión.

## Referencias de pruebas

La [matriz de casos](MATRIZ_CASOS.md) detalla los datos, resultados esperados y
las técnicas de diseño. El [registro de ejecución](REGISTRO_EJECUCION.md)
contiene los resultados observados y los enlaces a los reportes.
