# Matriz de casos del Entregable 2

22 casos por API, 44 en total.
Los pasos `.vN` verifican persistencia y efectos; no se cuentan como casos adicionales.
Precondición común: cargar datos_demo.json en la base aislada y ejecutar B01…B22, luego M01…M22.
Todos los resultados de esta matriz son **esperados**, no ejecuciones acreditadas.

| Caso | HU / CA propuesto | Objetivo | Técnica | Petición | Esperado |
|---|---|---|---|---|---|
| B01 | US-01 / B-CA1,B-CA4 | Registro válido con médico existente | Equivalencia válida / negocio | `POST /api/bebes/` | 201; comprobar cuerpo y pasos posteriores |
| B02 | US-01 / B-CA2 | Identificador obligatorio ausente | Equivalencia inválida | `POST /api/bebes/` | 400; comprobar cuerpo y pasos posteriores |
| B03 | US-01 / B-CA2 | Identificador ya registrado | Negocio: unicidad | `POST /api/bebes/` | 400; comprobar cuerpo y pasos posteriores |
| B04 | US-01 / B-CA2 | Nombre vacío | Equivalencia inválida | `POST /api/bebes/` | 400; comprobar cuerpo y pasos posteriores |
| B05 | US-01 / B-CA2 | Nombre de 199 caracteres | Límite superior de longitud | `POST /api/bebes/` | 201; comprobar cuerpo y pasos posteriores |
| B06 | US-01 / B-CA2 | Nombre de 200 caracteres | Límite superior de longitud | `POST /api/bebes/` | 201; comprobar cuerpo y pasos posteriores |
| B07 | US-01 / B-CA2 | Nombre de 201 caracteres | Límite superior de longitud | `POST /api/bebes/` | 400; comprobar cuerpo y pasos posteriores |
| B08 | US-01 / B-CA3 | Peso no numérico | Equivalencia inválida: tipo | `POST /api/bebes/` | 400; comprobar cuerpo y pasos posteriores |
| B09 | US-01 / B-CA3 | Peso -0.01 | Límite inferior: peso > 0 | `POST /api/bebes/` | 400; comprobar cuerpo y pasos posteriores |
| B10 | US-01 / B-CA3 | Peso 0 | Límite inferior: peso > 0 | `POST /api/bebes/` | 400; comprobar cuerpo y pasos posteriores |
| B11 | US-01 / B-CA3 | Peso 0.01 | Límite inferior: peso > 0 | `POST /api/bebes/` | 201; comprobar cuerpo y pasos posteriores |
| B12 | US-01 / B-CA3 | Peso y fecha opcionales nulos | Equivalencia válida: ausencia opcional | `POST /api/bebes/` | 201; comprobar cuerpo y pasos posteriores |
| B13 | US-01 / B-CA3 | Fecha de nacimiento: ayer | Límite temporal | `POST /api/bebes/` | 201; comprobar cuerpo y pasos posteriores |
| B14 | US-01 / B-CA3 | Fecha de nacimiento: hoy | Límite temporal | `POST /api/bebes/` | 201; comprobar cuerpo y pasos posteriores |
| B15 | US-01 / B-CA3 | Fecha de nacimiento: manana | Límite temporal | `POST /api/bebes/` | 400; comprobar cuerpo y pasos posteriores |
| B16 | US-01 / B-CA2 | Sexo fuera del catálogo | Equivalencia inválida: elección | `POST /api/bebes/` | 400; comprobar cuerpo y pasos posteriores |
| B17 | US-01 / B-CA4 | Médico inexistente | Negocio: integridad referencial | `POST /api/bebes/` | 400; comprobar cuerpo y pasos posteriores |
| B18 | US-01 / B-CA5 | Modificar diagnóstico sin perder otros datos | Negocio: actualización parcial | `PATCH /api/bebes/910001/` | 200; comprobar cuerpo y pasos posteriores |
| B19 | US-01 / B-CA3,B-CA5 | Edición inválida no guarda ni siquiera los campos válidos | Negocio: rechazo atómico | `PATCH /api/bebes/910001/` | 400; comprobar cuerpo y pasos posteriores |
| B20 | US-01 / B-CA5 | Consultar paciente inexistente | Equivalencia inválida: recurso | `GET /api/bebes/999999/` | 404; comprobar cuerpo y pasos posteriores |
| B21 | US-01 / B-CA5 | Recuperar datos para edición y relaciones | Negocio: precarga de edición | `GET /api/bebes/910001/` | 200; comprobar cuerpo y pasos posteriores |
| B22 | US-01 / B-CA6 | Eliminar paciente libera cuna y elimina medicación asociada | Negocio: cascada y SET_NULL (alcance adicional) | `DELETE /api/bebes/910003/` | 204; comprobar cuerpo y pasos posteriores |
| M01 | US-02 / M-CA1,M-CA3 | Registro válido en catálogo | Equivalencia válida | `POST /api/catalogo-medicamentos/` | 201; comprobar cuerpo y pasos posteriores |
| M02 | US-02 / M-CA1,M-CA3 | Nombre obligatorio | Equivalencia inválida | `POST /api/catalogo-medicamentos/` | 400; comprobar cuerpo y pasos posteriores |
| M03 | US-02 / M-CA1,M-CA3 | Principio activo vacío | Equivalencia inválida | `POST /api/catalogo-medicamentos/` | 400; comprobar cuerpo y pasos posteriores |
| M04 | US-02 / M-CA1,M-CA3 | Nombre de 150 caracteres | Límite superior | `POST /api/catalogo-medicamentos/` | 201; comprobar cuerpo y pasos posteriores |
| M05 | US-02 / M-CA1,M-CA3 | Nombre de 151 caracteres | Límite excedido | `POST /api/catalogo-medicamentos/` | 400; comprobar cuerpo y pasos posteriores |
| M06 | US-02 / M-CA1,M-CA3 | Principio activo de 150 caracteres | Límite superior | `POST /api/catalogo-medicamentos/` | 201; comprobar cuerpo y pasos posteriores |
| M07 | US-02 / M-CA1,M-CA3 | Principio activo de 151 caracteres | Límite excedido | `POST /api/catalogo-medicamentos/` | 400; comprobar cuerpo y pasos posteriores |
| M08 | US-02 / M-CA1,M-CA3 | Dosis no numérica | Equivalencia inválida | `POST /api/catalogo-medicamentos/` | 400; comprobar cuerpo y pasos posteriores |
| M09 | US-02 / M-CA1,M-CA3 | Dosis cero | Límite inferior excluido | `POST /api/catalogo-medicamentos/` | 400; comprobar cuerpo y pasos posteriores |
| M10 | US-02 / M-CA1,M-CA3 | Dosis mínima 0.01 mg | Límite inferior incluido | `POST /api/catalogo-medicamentos/` | 201; comprobar cuerpo y pasos posteriores |
| M11 | US-02 / M-CA1,M-CA3 | Dosis con exceso de decimales | Precisión decimal | `POST /api/catalogo-medicamentos/` | 400; comprobar cuerpo y pasos posteriores |
| M12 | US-02 / M-CA1,M-CA3 | Stock cero | Límite inferior excluido | `POST /api/catalogo-medicamentos/` | 400; comprobar cuerpo y pasos posteriores |
| M13 | US-02 / M-CA1,M-CA3 | Stock mínimo una unidad | Límite inferior incluido | `POST /api/catalogo-medicamentos/` | 201; comprobar cuerpo y pasos posteriores |
| M14 | US-02 / M-CA1,M-CA3 | Stock fraccionario | Equivalencia inválida | `POST /api/catalogo-medicamentos/` | 400; comprobar cuerpo y pasos posteriores |
| M15 | US-02 / M-CA1,M-CA3 | Stock obligatorio | Equivalencia inválida | `POST /api/catalogo-medicamentos/` | 400; comprobar cuerpo y pasos posteriores |
| M16 | US-02 / M-CA1,M-CA3 | Dosis obligatoria | Equivalencia inválida | `POST /api/catalogo-medicamentos/` | 400; comprobar cuerpo y pasos posteriores |
| M17 | US-02 / M-CA2 | Consulta para precarga | Negocio: recuperar producto | `GET /api/catalogo-medicamentos/910001/` | 200; comprobar cuerpo y pasos posteriores |
| M18 | US-02 / M-CA2 | Modificar stock y conservar otros campos | Negocio: persistencia | `PATCH /api/catalogo-medicamentos/910001/` | 200; comprobar cuerpo y pasos posteriores |
| M19 | US-02 / M-CA2,M-CA3 | Edición inválida no guarda cambios parciales | Negocio: rechazo atómico | `PATCH /api/catalogo-medicamentos/910001/` | 400; comprobar cuerpo y pasos posteriores |
| M20 | US-02 / M-CA2 | Producto inexistente | Equivalencia inválida | `GET /api/catalogo-medicamentos/999999/` | 404; comprobar cuerpo y pasos posteriores |
| M21 | US-02 / M-CA2 | Modificar todos los campos | Negocio: actualización completa | `PUT /api/catalogo-medicamentos/910001/` | 200; comprobar cuerpo y pasos posteriores |
| M22 | US-02 / M-CA2,M-CA3 | PUT incompleto conserva el producto | Negocio: campos requeridos | `PUT /api/catalogo-medicamentos/910001/` | 400; comprobar cuerpo y pasos posteriores |

## Datos y aserciones exactas por caso

Las cadenas largas se incluyen completas en la colección; aquí se muestra el mismo contenido fuente.

### B01 — Registro válido con médico existente

```json
[
  {
    "method": "POST",
    "path": "/api/bebes/",
    "status": 201,
    "body": {
      "identificador": "QA-B01",
      "nombre_completo": "Paciente ficticio QA",
      "edad_meses": 0,
      "sexo": "F",
      "peso": 3.2,
      "fecha_nacimiento": "{{ayer}}",
      "medico_a_cargo": 910001
    },
    "equals": {
      "identificador": "QA-B01",
      "nombre_completo": "Paciente ficticio QA",
      "edad_meses": 0,
      "sexo": "F",
      "peso": 3.2,
      "fecha_nacimiento": "{{ayer}}",
      "medico_a_cargo": 910001
    }
  },
  {
    "method": "GET",
    "path": "/api/bebes/",
    "status": 200,
    "length": 4
  }
]
```

### B02 — Identificador obligatorio ausente

```json
[
  {
    "method": "POST",
    "path": "/api/bebes/",
    "status": 400,
    "body": {
      "nombre_completo": "Paciente ficticio QA",
      "edad_meses": 0,
      "sexo": "F",
      "peso": 3.2,
      "fecha_nacimiento": "{{ayer}}",
      "medico_a_cargo": 910001
    },
    "keys": [
      "identificador"
    ]
  },
  {
    "method": "GET",
    "path": "/api/bebes/",
    "status": 200,
    "length": 4
  }
]
```

### B03 — Identificador ya registrado

```json
[
  {
    "method": "POST",
    "path": "/api/bebes/",
    "status": 400,
    "body": {
      "identificador": "QA-BASE-1",
      "nombre_completo": "Paciente ficticio QA",
      "edad_meses": 0,
      "sexo": "F",
      "peso": 3.2,
      "fecha_nacimiento": "{{ayer}}",
      "medico_a_cargo": 910001
    },
    "keys": [
      "identificador"
    ]
  },
  {
    "method": "GET",
    "path": "/api/bebes/",
    "status": 200,
    "length": 4
  }
]
```

### B04 — Nombre vacío

```json
[
  {
    "method": "POST",
    "path": "/api/bebes/",
    "status": 400,
    "body": {
      "identificador": "QA-B04",
      "nombre_completo": "",
      "edad_meses": 0,
      "sexo": "F",
      "peso": 3.2,
      "fecha_nacimiento": "{{ayer}}",
      "medico_a_cargo": 910001
    },
    "keys": [
      "nombre_completo"
    ]
  },
  {
    "method": "GET",
    "path": "/api/bebes/?identificador=QA-B04",
    "status": 200,
    "length": 0
  },
  {
    "method": "GET",
    "path": "/api/bebes/",
    "status": 200,
    "length": 4
  }
]
```

### B05 — Nombre de 199 caracteres

```json
[
  {
    "method": "POST",
    "path": "/api/bebes/",
    "status": 201,
    "body": {
      "identificador": "QA-B05",
      "nombre_completo": "NNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN",
      "edad_meses": 0,
      "sexo": "F",
      "peso": 3.2,
      "fecha_nacimiento": "{{ayer}}",
      "medico_a_cargo": 910001
    },
    "equals": {
      "identificador": "QA-B05",
      "nombre_completo": "NNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN",
      "edad_meses": 0,
      "sexo": "F",
      "peso": 3.2,
      "fecha_nacimiento": "{{ayer}}",
      "medico_a_cargo": 910001
    }
  },
  {
    "method": "GET",
    "path": "/api/bebes/",
    "status": 200,
    "length": 5
  }
]
```

### B06 — Nombre de 200 caracteres

```json
[
  {
    "method": "POST",
    "path": "/api/bebes/",
    "status": 201,
    "body": {
      "identificador": "QA-B06",
      "nombre_completo": "NNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN",
      "edad_meses": 0,
      "sexo": "F",
      "peso": 3.2,
      "fecha_nacimiento": "{{ayer}}",
      "medico_a_cargo": 910001
    },
    "equals": {
      "identificador": "QA-B06",
      "nombre_completo": "NNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN",
      "edad_meses": 0,
      "sexo": "F",
      "peso": 3.2,
      "fecha_nacimiento": "{{ayer}}",
      "medico_a_cargo": 910001
    }
  },
  {
    "method": "GET",
    "path": "/api/bebes/",
    "status": 200,
    "length": 6
  }
]
```

### B07 — Nombre de 201 caracteres

```json
[
  {
    "method": "POST",
    "path": "/api/bebes/",
    "status": 400,
    "body": {
      "identificador": "QA-B07",
      "nombre_completo": "NNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN",
      "edad_meses": 0,
      "sexo": "F",
      "peso": 3.2,
      "fecha_nacimiento": "{{ayer}}",
      "medico_a_cargo": 910001
    },
    "keys": [
      "nombre_completo"
    ]
  },
  {
    "method": "GET",
    "path": "/api/bebes/?identificador=QA-B07",
    "status": 200,
    "length": 0
  },
  {
    "method": "GET",
    "path": "/api/bebes/",
    "status": 200,
    "length": 6
  }
]
```

### B08 — Peso no numérico

```json
[
  {
    "method": "POST",
    "path": "/api/bebes/",
    "status": 400,
    "body": {
      "identificador": "QA-B08",
      "nombre_completo": "Paciente ficticio QA",
      "edad_meses": 0,
      "sexo": "F",
      "peso": "abc",
      "fecha_nacimiento": "{{ayer}}",
      "medico_a_cargo": 910001
    },
    "keys": [
      "peso"
    ]
  },
  {
    "method": "GET",
    "path": "/api/bebes/?identificador=QA-B08",
    "status": 200,
    "length": 0
  },
  {
    "method": "GET",
    "path": "/api/bebes/",
    "status": 200,
    "length": 6
  }
]
```

### B09 — Peso -0.01

```json
[
  {
    "method": "POST",
    "path": "/api/bebes/",
    "status": 400,
    "body": {
      "identificador": "QA-B09",
      "nombre_completo": "Paciente ficticio QA",
      "edad_meses": 0,
      "sexo": "F",
      "peso": -0.01,
      "fecha_nacimiento": "{{ayer}}",
      "medico_a_cargo": 910001
    },
    "keys": [
      "peso"
    ]
  },
  {
    "method": "GET",
    "path": "/api/bebes/?identificador=QA-B09",
    "status": 200,
    "length": 0
  },
  {
    "method": "GET",
    "path": "/api/bebes/",
    "status": 200,
    "length": 6
  }
]
```

### B10 — Peso 0

```json
[
  {
    "method": "POST",
    "path": "/api/bebes/",
    "status": 400,
    "body": {
      "identificador": "QA-B10",
      "nombre_completo": "Paciente ficticio QA",
      "edad_meses": 0,
      "sexo": "F",
      "peso": 0,
      "fecha_nacimiento": "{{ayer}}",
      "medico_a_cargo": 910001
    },
    "keys": [
      "peso"
    ]
  },
  {
    "method": "GET",
    "path": "/api/bebes/?identificador=QA-B10",
    "status": 200,
    "length": 0
  },
  {
    "method": "GET",
    "path": "/api/bebes/",
    "status": 200,
    "length": 6
  }
]
```

### B11 — Peso 0.01

```json
[
  {
    "method": "POST",
    "path": "/api/bebes/",
    "status": 201,
    "body": {
      "identificador": "QA-B11",
      "nombre_completo": "Paciente ficticio QA",
      "edad_meses": 0,
      "sexo": "F",
      "peso": 0.01,
      "fecha_nacimiento": "{{ayer}}",
      "medico_a_cargo": 910001
    },
    "equals": {
      "identificador": "QA-B11",
      "nombre_completo": "Paciente ficticio QA",
      "edad_meses": 0,
      "sexo": "F",
      "peso": 0.01,
      "fecha_nacimiento": "{{ayer}}",
      "medico_a_cargo": 910001
    }
  },
  {
    "method": "GET",
    "path": "/api/bebes/",
    "status": 200,
    "length": 7
  }
]
```

### B12 — Peso y fecha opcionales nulos

```json
[
  {
    "method": "POST",
    "path": "/api/bebes/",
    "status": 201,
    "body": {
      "identificador": "QA-B12",
      "nombre_completo": "Paciente ficticio QA",
      "edad_meses": 0,
      "sexo": "F",
      "peso": null,
      "fecha_nacimiento": null,
      "medico_a_cargo": 910001
    },
    "equals": {
      "identificador": "QA-B12",
      "nombre_completo": "Paciente ficticio QA",
      "edad_meses": 0,
      "sexo": "F",
      "peso": null,
      "fecha_nacimiento": null,
      "medico_a_cargo": 910001
    }
  },
  {
    "method": "GET",
    "path": "/api/bebes/",
    "status": 200,
    "length": 8
  }
]
```

### B13 — Fecha de nacimiento: ayer

```json
[
  {
    "method": "POST",
    "path": "/api/bebes/",
    "status": 201,
    "body": {
      "identificador": "QA-B13",
      "nombre_completo": "Paciente ficticio QA",
      "edad_meses": 0,
      "sexo": "F",
      "peso": 3.2,
      "fecha_nacimiento": "{{ayer}}",
      "medico_a_cargo": 910001
    },
    "equals": {
      "identificador": "QA-B13",
      "nombre_completo": "Paciente ficticio QA",
      "edad_meses": 0,
      "sexo": "F",
      "peso": 3.2,
      "fecha_nacimiento": "{{ayer}}",
      "medico_a_cargo": 910001
    }
  },
  {
    "method": "GET",
    "path": "/api/bebes/",
    "status": 200,
    "length": 9
  }
]
```

### B14 — Fecha de nacimiento: hoy

```json
[
  {
    "method": "POST",
    "path": "/api/bebes/",
    "status": 201,
    "body": {
      "identificador": "QA-B14",
      "nombre_completo": "Paciente ficticio QA",
      "edad_meses": 0,
      "sexo": "F",
      "peso": 3.2,
      "fecha_nacimiento": "{{hoy}}",
      "medico_a_cargo": 910001
    },
    "equals": {
      "identificador": "QA-B14",
      "nombre_completo": "Paciente ficticio QA",
      "edad_meses": 0,
      "sexo": "F",
      "peso": 3.2,
      "fecha_nacimiento": "{{hoy}}",
      "medico_a_cargo": 910001
    }
  },
  {
    "method": "GET",
    "path": "/api/bebes/",
    "status": 200,
    "length": 10
  }
]
```

### B15 — Fecha de nacimiento: manana

```json
[
  {
    "method": "POST",
    "path": "/api/bebes/",
    "status": 400,
    "body": {
      "identificador": "QA-B15",
      "nombre_completo": "Paciente ficticio QA",
      "edad_meses": 0,
      "sexo": "F",
      "peso": 3.2,
      "fecha_nacimiento": "{{manana}}",
      "medico_a_cargo": 910001
    },
    "keys": [
      "fecha_nacimiento"
    ]
  },
  {
    "method": "GET",
    "path": "/api/bebes/?identificador=QA-B15",
    "status": 200,
    "length": 0
  },
  {
    "method": "GET",
    "path": "/api/bebes/",
    "status": 200,
    "length": 10
  }
]
```

### B16 — Sexo fuera del catálogo

```json
[
  {
    "method": "POST",
    "path": "/api/bebes/",
    "status": 400,
    "body": {
      "identificador": "QA-B16",
      "nombre_completo": "Paciente ficticio QA",
      "edad_meses": 0,
      "sexo": "X",
      "peso": 3.2,
      "fecha_nacimiento": "{{ayer}}",
      "medico_a_cargo": 910001
    },
    "keys": [
      "sexo"
    ]
  },
  {
    "method": "GET",
    "path": "/api/bebes/?identificador=QA-B16",
    "status": 200,
    "length": 0
  },
  {
    "method": "GET",
    "path": "/api/bebes/",
    "status": 200,
    "length": 10
  }
]
```

### B17 — Médico inexistente

```json
[
  {
    "method": "POST",
    "path": "/api/bebes/",
    "status": 400,
    "body": {
      "identificador": "QA-B17",
      "nombre_completo": "Paciente ficticio QA",
      "edad_meses": 0,
      "sexo": "F",
      "peso": 3.2,
      "fecha_nacimiento": "{{ayer}}",
      "medico_a_cargo": 999999
    },
    "keys": [
      "medico_a_cargo"
    ]
  },
  {
    "method": "GET",
    "path": "/api/bebes/?identificador=QA-B17",
    "status": 200,
    "length": 0
  },
  {
    "method": "GET",
    "path": "/api/bebes/",
    "status": 200,
    "length": 10
  }
]
```

### B18 — Modificar diagnóstico sin perder otros datos

```json
[
  {
    "method": "PATCH",
    "path": "/api/bebes/910001/",
    "status": 200,
    "body": {
      "diagnostico": "Observación QA actualizada"
    },
    "equals": {
      "diagnostico": "Observación QA actualizada",
      "identificador": "QA-BASE-1",
      "peso": 3.2,
      "medico_a_cargo": 910001
    }
  },
  {
    "method": "GET",
    "path": "/api/bebes/910001/",
    "status": 200,
    "equals": {
      "diagnostico": "Observación QA actualizada",
      "peso": 3.2,
      "medico_a_cargo": 910001
    }
  }
]
```

### B19 — Edición inválida no guarda ni siquiera los campos válidos

```json
[
  {
    "method": "PATCH",
    "path": "/api/bebes/910001/",
    "status": 400,
    "body": {
      "peso": 0,
      "diagnostico": "NO DEBE GUARDARSE"
    },
    "keys": [
      "peso"
    ]
  },
  {
    "method": "GET",
    "path": "/api/bebes/910001/",
    "status": 200,
    "equals": {
      "peso": 3.2,
      "diagnostico": "Observación QA actualizada"
    }
  }
]
```

### B20 — Consultar paciente inexistente

```json
[
  {
    "method": "GET",
    "path": "/api/bebes/999999/",
    "status": 404,
    "keys": [
      "detail"
    ]
  }
]
```

### B21 — Recuperar datos para edición y relaciones

```json
[
  {
    "method": "GET",
    "path": "/api/bebes/910001/",
    "status": 200,
    "equals": {
      "identificador": "QA-BASE-1",
      "medico_nombre": "Profesional ficticio QA",
      "cuna": "QA-CUNA-1",
      "medicamentos.0.id": 910001
    }
  }
]
```

### B22 — Eliminar paciente libera cuna y elimina medicación asociada

```json
[
  {
    "method": "DELETE",
    "path": "/api/bebes/910003/",
    "status": 204
  },
  {
    "method": "GET",
    "path": "/api/bebes/910003/",
    "status": 404,
    "keys": [
      "detail"
    ]
  },
  {
    "method": "GET",
    "path": "/api/medicamentos/910003/",
    "status": 404,
    "keys": [
      "detail"
    ]
  },
  {
    "method": "GET",
    "path": "/api/cunas/910002/",
    "status": 200,
    "equals": {
      "paciente": null
    }
  }
]
```

### M01 — Registro válido en catálogo

```json
[
  {
    "method": "POST",
    "path": "/api/catalogo-medicamentos/",
    "status": 201,
    "body": {
      "nombre": "Producto ficticio M01",
      "principio_activo": "Sustancia QA",
      "dosis_mg": "1.00",
      "stock": 10
    },
    "equals": {
      "nombre": "Producto ficticio M01",
      "principio_activo": "Sustancia QA",
      "dosis_mg": "1.00",
      "stock": 10
    }
  },
  {
    "method": "GET",
    "path": "/api/catalogo-medicamentos/",
    "status": 200,
    "length": 2
  }
]
```

### M02 — Nombre obligatorio

```json
[
  {
    "method": "POST",
    "path": "/api/catalogo-medicamentos/",
    "status": 400,
    "body": {
      "principio_activo": "Sustancia QA",
      "dosis_mg": "1.00",
      "stock": 10
    },
    "keys": [
      "nombre"
    ]
  },
  {
    "method": "GET",
    "path": "/api/catalogo-medicamentos/",
    "status": 200,
    "length": 2
  }
]
```

### M03 — Principio activo vacío

```json
[
  {
    "method": "POST",
    "path": "/api/catalogo-medicamentos/",
    "status": 400,
    "body": {
      "nombre": "Producto ficticio M03",
      "principio_activo": " ",
      "dosis_mg": "1.00",
      "stock": 10
    },
    "keys": [
      "principio_activo"
    ]
  },
  {
    "method": "GET",
    "path": "/api/catalogo-medicamentos/",
    "status": 200,
    "length": 2
  }
]
```

### M04 — Nombre de 150 caracteres

```json
[
  {
    "method": "POST",
    "path": "/api/catalogo-medicamentos/",
    "status": 201,
    "body": {
      "nombre": "NNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN",
      "principio_activo": "Sustancia QA",
      "dosis_mg": "1.00",
      "stock": 10
    },
    "equals": {
      "nombre": "NNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN",
      "principio_activo": "Sustancia QA",
      "dosis_mg": "1.00",
      "stock": 10
    }
  },
  {
    "method": "GET",
    "path": "/api/catalogo-medicamentos/",
    "status": 200,
    "length": 3
  }
]
```

### M05 — Nombre de 151 caracteres

```json
[
  {
    "method": "POST",
    "path": "/api/catalogo-medicamentos/",
    "status": 400,
    "body": {
      "nombre": "NNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNNN",
      "principio_activo": "Sustancia QA",
      "dosis_mg": "1.00",
      "stock": 10
    },
    "keys": [
      "nombre"
    ]
  },
  {
    "method": "GET",
    "path": "/api/catalogo-medicamentos/",
    "status": 200,
    "length": 3
  }
]
```

### M06 — Principio activo de 150 caracteres

```json
[
  {
    "method": "POST",
    "path": "/api/catalogo-medicamentos/",
    "status": 201,
    "body": {
      "nombre": "Producto ficticio M06",
      "principio_activo": "PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP",
      "dosis_mg": "1.00",
      "stock": 10
    },
    "equals": {
      "nombre": "Producto ficticio M06",
      "principio_activo": "PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP",
      "dosis_mg": "1.00",
      "stock": 10
    }
  },
  {
    "method": "GET",
    "path": "/api/catalogo-medicamentos/",
    "status": 200,
    "length": 4
  }
]
```

### M07 — Principio activo de 151 caracteres

```json
[
  {
    "method": "POST",
    "path": "/api/catalogo-medicamentos/",
    "status": 400,
    "body": {
      "nombre": "Producto ficticio M07",
      "principio_activo": "PPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPPP",
      "dosis_mg": "1.00",
      "stock": 10
    },
    "keys": [
      "principio_activo"
    ]
  },
  {
    "method": "GET",
    "path": "/api/catalogo-medicamentos/",
    "status": 200,
    "length": 4
  }
]
```

### M08 — Dosis no numérica

```json
[
  {
    "method": "POST",
    "path": "/api/catalogo-medicamentos/",
    "status": 400,
    "body": {
      "nombre": "Producto ficticio M08",
      "principio_activo": "Sustancia QA",
      "dosis_mg": "abc",
      "stock": 10
    },
    "keys": [
      "dosis_mg"
    ]
  },
  {
    "method": "GET",
    "path": "/api/catalogo-medicamentos/",
    "status": 200,
    "length": 4
  }
]
```

### M09 — Dosis cero

```json
[
  {
    "method": "POST",
    "path": "/api/catalogo-medicamentos/",
    "status": 400,
    "body": {
      "nombre": "Producto ficticio M09",
      "principio_activo": "Sustancia QA",
      "dosis_mg": "0.00",
      "stock": 10
    },
    "keys": [
      "dosis_mg"
    ]
  },
  {
    "method": "GET",
    "path": "/api/catalogo-medicamentos/",
    "status": 200,
    "length": 4
  }
]
```

### M10 — Dosis mínima 0.01 mg

```json
[
  {
    "method": "POST",
    "path": "/api/catalogo-medicamentos/",
    "status": 201,
    "body": {
      "nombre": "Producto ficticio M10",
      "principio_activo": "Sustancia QA",
      "dosis_mg": "0.01",
      "stock": 10
    },
    "equals": {
      "nombre": "Producto ficticio M10",
      "principio_activo": "Sustancia QA",
      "dosis_mg": "0.01",
      "stock": 10
    }
  },
  {
    "method": "GET",
    "path": "/api/catalogo-medicamentos/",
    "status": 200,
    "length": 5
  }
]
```

### M11 — Dosis con exceso de decimales

```json
[
  {
    "method": "POST",
    "path": "/api/catalogo-medicamentos/",
    "status": 400,
    "body": {
      "nombre": "Producto ficticio M11",
      "principio_activo": "Sustancia QA",
      "dosis_mg": "0.001",
      "stock": 10
    },
    "keys": [
      "dosis_mg"
    ]
  },
  {
    "method": "GET",
    "path": "/api/catalogo-medicamentos/",
    "status": 200,
    "length": 5
  }
]
```

### M12 — Stock cero

```json
[
  {
    "method": "POST",
    "path": "/api/catalogo-medicamentos/",
    "status": 400,
    "body": {
      "nombre": "Producto ficticio M12",
      "principio_activo": "Sustancia QA",
      "dosis_mg": "1.00",
      "stock": 0
    },
    "keys": [
      "stock"
    ]
  },
  {
    "method": "GET",
    "path": "/api/catalogo-medicamentos/",
    "status": 200,
    "length": 5
  }
]
```

### M13 — Stock mínimo una unidad

```json
[
  {
    "method": "POST",
    "path": "/api/catalogo-medicamentos/",
    "status": 201,
    "body": {
      "nombre": "Producto ficticio M13",
      "principio_activo": "Sustancia QA",
      "dosis_mg": "1.00",
      "stock": 1
    },
    "equals": {
      "nombre": "Producto ficticio M13",
      "principio_activo": "Sustancia QA",
      "dosis_mg": "1.00",
      "stock": 1
    }
  },
  {
    "method": "GET",
    "path": "/api/catalogo-medicamentos/",
    "status": 200,
    "length": 6
  }
]
```

### M14 — Stock fraccionario

```json
[
  {
    "method": "POST",
    "path": "/api/catalogo-medicamentos/",
    "status": 400,
    "body": {
      "nombre": "Producto ficticio M14",
      "principio_activo": "Sustancia QA",
      "dosis_mg": "1.00",
      "stock": 1.5
    },
    "keys": [
      "stock"
    ]
  },
  {
    "method": "GET",
    "path": "/api/catalogo-medicamentos/",
    "status": 200,
    "length": 6
  }
]
```

### M15 — Stock obligatorio

```json
[
  {
    "method": "POST",
    "path": "/api/catalogo-medicamentos/",
    "status": 400,
    "body": {
      "nombre": "Producto ficticio M15",
      "principio_activo": "Sustancia QA",
      "dosis_mg": "1.00"
    },
    "keys": [
      "stock"
    ]
  },
  {
    "method": "GET",
    "path": "/api/catalogo-medicamentos/",
    "status": 200,
    "length": 6
  }
]
```

### M16 — Dosis obligatoria

```json
[
  {
    "method": "POST",
    "path": "/api/catalogo-medicamentos/",
    "status": 400,
    "body": {
      "nombre": "Producto ficticio M16",
      "principio_activo": "Sustancia QA",
      "stock": 10
    },
    "keys": [
      "dosis_mg"
    ]
  },
  {
    "method": "GET",
    "path": "/api/catalogo-medicamentos/",
    "status": 200,
    "length": 6
  }
]
```

### M17 — Consulta para precarga

```json
[
  {
    "method": "GET",
    "path": "/api/catalogo-medicamentos/910001/",
    "status": 200,
    "equals": {
      "nombre": "Producto base QA",
      "principio_activo": "Sustancia QA",
      "dosis_mg": "1.00",
      "stock": 10
    }
  }
]
```

### M18 — Modificar stock y conservar otros campos

```json
[
  {
    "method": "PATCH",
    "path": "/api/catalogo-medicamentos/910001/",
    "status": 200,
    "body": {
      "stock": 5
    },
    "equals": {
      "stock": 5,
      "dosis_mg": "1.00"
    }
  },
  {
    "method": "GET",
    "path": "/api/catalogo-medicamentos/910001/",
    "status": 200,
    "equals": {
      "stock": 5,
      "nombre": "Producto base QA"
    }
  }
]
```

### M19 — Edición inválida no guarda cambios parciales

```json
[
  {
    "method": "PATCH",
    "path": "/api/catalogo-medicamentos/910001/",
    "status": 400,
    "body": {
      "stock": -1,
      "nombre": "NO GUARDAR"
    },
    "keys": [
      "stock"
    ]
  },
  {
    "method": "GET",
    "path": "/api/catalogo-medicamentos/910001/",
    "status": 200,
    "equals": {
      "stock": 5,
      "nombre": "Producto base QA"
    }
  }
]
```

### M20 — Producto inexistente

```json
[
  {
    "method": "GET",
    "path": "/api/catalogo-medicamentos/999999/",
    "status": 404,
    "keys": [
      "detail"
    ]
  }
]
```

### M21 — Modificar todos los campos

```json
[
  {
    "method": "PUT",
    "path": "/api/catalogo-medicamentos/910001/",
    "status": 200,
    "body": {
      "nombre": "Producto actualizado QA",
      "principio_activo": "Sustancia nueva QA",
      "dosis_mg": "2.50",
      "stock": 20
    }
  },
  {
    "method": "GET",
    "path": "/api/catalogo-medicamentos/910001/",
    "status": 200,
    "equals": {
      "nombre": "Producto actualizado QA",
      "principio_activo": "Sustancia nueva QA",
      "dosis_mg": "2.50",
      "stock": 20
    }
  }
]
```

### M22 — PUT incompleto conserva el producto

```json
[
  {
    "method": "PUT",
    "path": "/api/catalogo-medicamentos/910001/",
    "status": 400,
    "body": {
      "nombre": "NO GUARDAR"
    },
    "keys": [
      "principio_activo",
      "dosis_mg",
      "stock"
    ]
  },
  {
    "method": "GET",
    "path": "/api/catalogo-medicamentos/910001/",
    "status": 200,
    "equals": {
      "nombre": "Producto actualizado QA",
      "stock": 20
    }
  }
]
```
