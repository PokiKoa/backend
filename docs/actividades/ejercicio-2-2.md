# Ejercicio 2.2: Construcción para la Verificación en el Proyecto

**Proyecto:** Poki-Koa — Sistema de Monitoreo Neonatal  
**Rama:** `feature/54-construccion-para-verificacion`  
**Issue:** #54  

---

## Ficha de Operación 1

| Elemento | Registro del equipo |
| :--- | :--- |
| **Funcionalidad y operación** | **Funcionalidad:** Registro y actualización de telemetría de constantes vitales en cunas neonatales.<br>**Clase, módulo y firma:** `src/cunas/services.py` → `CunaService.actualizar_telemetria(cuna_id: str, ritmo_cardiaco: int, spo2: int, temperatura: float) -> Cuna` |
| **Propósito** | Actualizar de forma segura las constantes fisiológicas de una cuna en monitoreo activo, garantizando que los datos recibidos desde los sensores sean biológicamente válidos antes de persistirlos. |
| **Precondiciones** | 1. `cuna_id` debe ser una cadena no vacía correspondiente a una cuna existente.<br>2. `ritmo_cardiaco` debe estar entre 30 y 250 bpm; `spo2` debe ser un porcentaje entero entre 50 y 100; `temperatura` debe ser un número entre 30.0 y 45.0 °C. |
| **Postcondiciones** | 1. La cuna persiste los nuevos valores en base de datos junto con su marca de tiempo en `ultima_actualizacion`.<br>2. Se retorna la instancia de la cuna con los datos actualizados y confirmados. |
| **Invariante** | Una cuna persistida en el sistema nunca puede tener un `spo2` superior al 100% ni inferior al 0%, y siempre debe conservar un `id` primario asignado. |
| **Validación defensiva** | • **Entrada inválida 1:** `spo2 = 110` → **Respuesta:** Lanza `ValueError("SpO2 inválido: 110. Debe ser un porcentaje entre 50% y 100%.")`<br>• **Entrada inválida 2:** `cuna_id = ""` o `None` → **Respuesta:** Lanza `ValueError("cuna_id es obligatorio y no puede estar vacío.")` |
| **Dependencia explícita** | Se inyecta la clase del modelo o repositorio (`cuna_model`) mediante el constructor `CunaService(cuna_model=Cuna)`. En entornos de prueba, se reemplaza por un `Mock()` para verificar la lógica sin tocar la base de datos real ni acoplarse al ORM. |
| **Evidencia de ejecución** | **Comando ejecutado:**<br>`uv run poki_koa test cunas.tests.CunaServiceContractTestCase -v 2`<br><br>**Salida de ejecución en consola:**<br>```text<br>Found 5 test(s).<br>Creating test database for alias 'default'...<br>System check identified no issues (0 silenced).<br>.....<br>----------------------------------------------------------------------<br>Ran 5 tests in 0.003s<br><br>OK<br>Destroying test database for alias 'default'...<br>```<br>Pruebas específicas de contrato verificadas (100% de cobertura en `src/cunas/services.py`):<br>• `test_caso_valido_actualizacion_exitosa`: Actualización de telemetría válida.<br>• `test_caso_invalido_spo2_fuera_de_rango`: Rechazo con `ValueError` por SpO2 > 100.<br>• `test_caso_invalido_cuna_id_vacio`: Rechazo con `ValueError` por identificador vacío.<br>• `test_caso_invalido_ritmo_cardiaco_y_temperatura_fuera_de_rango`: Rechazo de FC y temperatura fuera de rango fisiológico.<br>• `test_cuna_inexistente_lanza_lookup_error`: Traducción de `DoesNotExist` a `LookupError`. |

---

## Ficha de Operación 2: Contrato y aserciones para gestión de alertas

**Issue:** #54 — Construcción para la Verificación

**Rama de desarrollo:** `feature/54-gestion-alertas`

**Operación:** `AlertaService.resolver_alerta(alerta_id)`

**Estado:** Implementada y verificada.

> **Nota de trazabilidad:** La Operación 2 se desarrolló en la rama `feature/54-gestion-alertas`. Su implementación incorpora contratos explícitos, validaciones defensivas, aserciones para invariantes internas e inyección de dependencias. Se integra con el endpoint existente de resolución de alertas y cuenta con pruebas unitarias y de integración.

| Elemento | Registro del equipo |
| :--- | :--- |
| **Funcionalidad y operación** | **Funcionalidad:** Resolución de alertas activas de monitoreo neonatal.<br>**Clase, módulo y firma:** `src/cunas/alertas_service.py` → `AlertaService.resolver_alerta(alerta_id: int \| str) -> RegistroAlerta`.<br>**Repositorio:** `src/cunas/repositories_alertas.py` → `DjangoAlertaRepository`.<br>**Ruta:** `POST /api/alertas/{id}/resolver/`. |
| **Propósito** | Resolver una alerta activa mediante un servicio de negocio con contrato explícito, garantizando el cambio de estado a `activa=False`, la validación de entradas y la conservación de los demás datos del registro. |
| **Precondiciones** | 1. `alerta_id` debe ser un entero positivo entre 1 y `2**63 - 1`, o una cadena decimal ASCII canónica, sin espacios, signos ni ceros iniciales.<br>2. La alerta debe existir.<br>3. La alerta debe estar activa (`activa=True`) al momento de su resolución. |
| **Postcondiciones** | 1. La alerta queda inactiva (`activa=False`) mediante una actualización condicional persistida en la base de datos.<br>2. El servicio devuelve un `RegistroAlerta` con el estado actualizado.<br>3. La resolución exitosa devuelve HTTP 200 desde el endpoint. |
| **Invariante** | Se conserva el identificador y los demás campos de la alerta: `paciente_id`, `cuna_id`, `tipo`, `mensaje`, `nivel`, `fecha_hora` y `valor_leido`. Las aserciones internas verifican la identidad del registro y que el resultado del repositorio corresponda al registro original con únicamente `activa=False`. |
| **Validación defensiva** | **Entrada inválida 1:** `alerta_id="abc"` u otro identificador mal formado → `AlertaOperacionError`, HTTP 400, sin consultar ni modificar el repositorio.<br>**Entrada inválida 2:** alerta previamente resuelta (`activa=False`) → `AlertaEstadoNoPermitido`, HTTP 409, sin modificar el registro.<br>**Alerta inexistente:** `AlertaNoEncontrada`, HTTP 404.<br>**Cambio concurrente detectado:** se rechaza la resolución con `AlertaEstadoNoPermitido`, HTTP 409. |
| **Dependencia explícita** | `AlertaService` recibe mediante su constructor un repositorio que implementa el contrato `AlertaRepository`, definido con `Protocol` y los métodos `obtener` y `confirmar_activa`. La vista utiliza `DjangoAlertaRepository`, mientras que las pruebas unitarias utilizan un repositorio simulado (`RepositorioFake`) sin conexión a la base de datos. |
| **Evidencia de ejecución** | **Pruebas unitarias de la Operación 2:** `test/test_operacion2.py` → **7 pruebas, OK**.<br>**Pruebas de integración:** `src/cunas/test_operacion2_integracion.py` → **5 pruebas, OK**.<br>**Pruebas Django completas:** `uv run --locked python src/manage.py test cunas -v 1` → **52 pruebas, OK**.<br>**Pruebas unitarias generales:** `uv run --locked python -m unittest discover -s test -v` → **14 pruebas, OK**.<br>**Verificación del proyecto:** `uv run --locked python src/manage.py check` → Sin problemas detectados. |

### Evidencias complementarias de la Operación 2

**Prueba unitaria aislada:**

```powershell
$env:PYTHONPATH="src"
uv run --locked python -m unittest discover -s test -p "test_operacion2.py" -v
```

**Resultado:** 7 pruebas aprobadas.

**Prueba de integración con Django:**

```powershell
uv run --locked python src/manage.py test cunas.test_operacion2_integracion -v 2
```

**Resultado:** 5 pruebas aprobadas.

**Prueba de regresión del módulo:**

```powershell
uv run --locked python src/manage.py test cunas -v 1
```

**Resultado:** 52 pruebas aprobadas.

**Verificación general de pruebas unitarias:**

```powershell
$env:PYTHONPATH="src"
uv run --locked python -m unittest discover -s test -v
```

**Resultado:** 14 pruebas aprobadas, correspondientes a las operaciones 2 y 3.

**Observación de compatibilidad:** El endpoint devuelve HTTP 409 cuando se intenta resolver una alerta que ya está inactiva. Este comportamiento difiere de la implementación anterior, que devolvía HTTP 200.

---

## Ficha de Operación 3

| Elemento | Registro del equipo |
| :--- | :--- |
| **Funcionalidad y operación** | **Funcionalidad:** Confirmación de administración de medicamentos.<br>**Clase, módulo y firma:** `src/cunas/medicamentos.py` → `MedicamentoService.administrar(medicamento_id: int \| str) -> RegistroMedicamento`.<br>**Ruta:** `POST /api/medicamentos/{id}/administrar/`, sin cuerpo requerido. |
| **Propósito** | Registrar un medicamento pendiente como `Administrado` y devolver su ID, paciente y estado mediante HTTP 200. |
| **Precondiciones** | 1. El ID debe ser un entero entre 1 y `2**63 - 1`, o una cadena decimal ASCII equivalente sin espacios, signos ni ceros iniciales; no se aceptan nulos, vacíos ni booleanos.<br>2. El medicamento debe existir y estar `Pendiente` al consultar y actualizar. |
| **Postcondiciones** | 1. Se persiste el estado `Administrado` y se devuelve el registro actualizado.<br>2. Se conservan el ID, el paciente y los demás campos; una confirmación repetida se rechaza con HTTP 409 mientras siga administrado. |
| **Invariante** | El medicamento pertenece a un paciente con ID entero positivo y conserva ambas identidades durante la transición. Las aserciones verifican estas reglas internas y el resultado `Administrado`. |
| **Validación defensiva** | **Entrada inválida 1:** `medicamento_id="abc"` → `OperacionError("medicamento_id debe ser un entero positivo.")`, HTTP 400, sin consultar ni escribir.<br>**Entrada inválida 2:** medicamento ya `Administrado` → `EstadoNoPermitido("Solo se puede administrar un medicamento Pendiente.")`, HTTP 409, sin modificar el registro. |
| **Dependencia explícita** | El constructor `MedicamentoService(repositorio)` recibe un `MedicamentoRepository` con los métodos `obtener` y `confirmar_pendiente`. La vista inyecta `DjangoMedicamentoRepository`; las pruebas usan `RepositorioFake` en memoria, sin Django ni base de datos. |
| **Evidencia de ejecución** | **Preparación:** `uv sync --locked` (usa las versiones de `uv.lock`).<br>**Prueba aislada:** `PYTHONPATH=src uv run --locked python -m unittest discover -s test -v` → 7 pruebas, `OK`.<br>**Archivo:** `test/test_operacion3.py`; verifica éxito, ID inválido y estado ya administrado, incluyendo conservación del estado ante rechazos.<br>**Integración:** `uv run --locked python src/manage.py test cunas -v 1` → 35 pruebas, `OK`, incluyendo las pruebas de la Operación 1 y `APIAdministrarMedicamentoTestCase`. |
