# Proceso de Depuración — Hito 2

Registro en 8 pasos del proceso de depuración realizado sobre el módulo de telemetría y alertas de cunas (`Issue #51`).

## 1. Síntoma detectado
Al enviar datos de sensores al endpoint `POST /api/cunas/{id}/telemetria/` con valores imposibles (como ritmo cardíaco negativo o saturación mayor a 100%), el sistema respondía `200 OK`, guardaba el dato corrupto en la cuna y creaba una alerta clínica falsa (`"Bradicardia severa: -15 bpm"`).

## 2. Reproducción del problema
Con el servidor arriba (`uv run poki_koa`), se reprodujo enviando:

```bash
curl -i -X POST "http://127.0.0.1:8000/api/cunas/1/telemetria/" \
  -H "Content-Type: application/json" \
  -d '{"ritmo_cardiaco": -15, "spo2": 140}'
```

También se reprodujo desde la suite de pruebas en `src/cunas/tests.py` (`APITelemetriaCunaTestCase`).

## 3. Hipótesis
1. En `CunaViewSet.telemetria` (`src/cunas/views.py`), los valores de `request.data` se copiaban directo al objeto `cuna` con `setattr()` y se llamaba a `cuna.save()` sin validar antes si estaban dentro de rangos posibles.
2. Como `Cuna` tiene conectada la señal `post_save` (`src/cunas/signals.py`), apenas se guardaba el `-15` se ejecutaba `procesar_alertas_cuna(cuna)` (`src/cunas/alertas.py`), donde la condición `fc < 80` lo tomaba como bradicardia crítica.

## 4. Colocación de breakpoints
Usando el perfil `Django: Depurar Pruebas (cunas)` de [`.vscode/launch.json`](../../.vscode/launch.json), se colocaron dos breakpoints:
- **Breakpoint 1:** `src/cunas/views.py` línea 170 (entrada de validaciones en `CunaViewSet.telemetria`).
- **Breakpoint 2:** `src/cunas/alertas.py` línea 234 (bucle `for anomalia in anomalias:` en `procesar_alertas_cuna`).

## 5. Ejecución paso a paso e inspección de variables
Avanzando con `Step Over (F10)` y `Step Into (F11)` se revisaron las variables en cada punto:

| Punto detenido | Variables inspeccionadas | Qué se observó |
|---|---|---|
| `views.py:170` (Breakpoint 1) | `data = {'ritmo_cardiaco': -15}`<br>`cuna.ritmo_cardiaco = 130`<br>`ritmo = -15` | La cuna tenía `130 bpm` guardados, pero el payload traía `-15`. |
| `views.py:172` (`Step Over`) | `1 <= ritmo <= 260` → `False` | Con la validación activa, entra al `if`, emite el log `WARNING` y retorna `HTTP 400` antes de llegar a `cuna.save()`. |
| `alertas.py:234` (Breakpoint 2, probando con `ritmo_cardiaco = 72`) | `anomalias = [{'tipo': 'ritmo_cardiaco', 'nivel': 'Critica', 'valor_leido': 72.0}]`<br>`alerta_activa = None` | Cuando el valor sí es válido pero crítico (`72 bpm`), pasa a `procesar_alertas_cuna` y crea la alerta (o la actualiza si ya existía una igual activa). |

## 6. Revisión de trazas y logs
Se configuró `LOGGING` en `src/poki_koa/settings.py` para ver las trazas del módulo `cunas` en consola:
- `logger.info`: registra la llegada de telemetría mostrando solo el identificador de la cuna (sin datos del paciente por privacidad).
- `logger.warning`: deja registro cuando se rechaza una lectura fuera de rango.

```text
[INFO] 2026-10-27 20:40:50 cunas.views: Recibida telemetría para cuna C-REG-01
[WARNING] 2026-10-27 20:40:50 cunas.views: Telemetría anómala detectada en cuna C-REG-01: ritmo cardíaco inválido (-15)
```

## 7. Causa raíz y corrección aplicada
La causa era que `telemetria` no validaba todos los campos en la frontera HTTP antes de guardar y que en Python `isinstance(True, int)` evalúa a `True`.

**Corrección en `src/cunas/views.py` (líneas 163–232) y justificación clínica:**
- Se distinguen **errores físicos/de sensor** (`HTTP 400`, no se guardan) de **anomalías clínicas reales** (`HTTP 200`, sí se guardan y activan alertas en `alertas.py`):
  - `ritmo_cardiaco`: acepta `1..260 bpm` (valores como `72` o `195` son posibles en neonatos y disparan alerta crítica; `<= 0` o `> 260` se rechazan con `400`).
  - `spo2`: acepta `0..100 %` (`< 95%` dispara alerta en `alertas.py`; `< 0` o `> 100` es error de lectura y devuelve `400`).
  - `temperatura`: acepta `25.0..45.0 °C` (`< 36.5` o `> 37.5` dispara alerta; fuera de `25..45 °C` devuelve `400`).
  - `estado_sueno`: solo `"Dormido"` o `"Despierto"`.
  - `canula_ok` y `via_iv_activa`: booleanos estrictos (`bool`).

## 8. Verificación del resultado
Se verificó con las pruebas de telemetría y regresión:

```bash
uv run poki_koa test cunas.tests.APITelemetriaCunaTestCase cunas.tests.RegresionSuiteTestCase -v 2
```

Todas las pruebas pasan (`OK`), confirmando que los valores inválidos devuelven `400 Bad Request` y no modifican la cuna ni crean alertas falsas.
