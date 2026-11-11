# Cambio a Bruno y ejecución de las pruebas

## Motivo del cambio

Al preparar la entrega con Thunder Client 2.41.7, la instalación gratuita mostró
«Collections are not supported in the free version». El equipo decidió utilizar
Bruno para ejecutar la colección completa, comprobar automáticamente las respuestas
y exportar los resultados sin enviar las solicitudes una por una.

El cambio conserva los 44 casos (22 por API), sus datos, su orden y sus verificaciones:
94 solicitudes y 265 pruebas automáticas. Los pasos `.vN` comprueban persistencia y
efectos de una solicitud; no cuentan como casos adicionales.

La herramienta solicitada en la evaluación es Thunder Client. Las pruebas registradas
en esta entrega se ejecutaron con Bruno; el cambio debe acordarse con el docente.

## Instalación

- [Página oficial de Bruno](https://www.usebruno.com/).
- [Descargas oficiales para Windows, macOS y Linux](https://www.usebruno.com/downloads).

En la página de descargas, seleccionar el sistema operativo y el paquete compatible
con la arquitectura del equipo. Instalar y abrir la aplicación de escritorio.
La versión utilizada y comprobada en esta entrega es **4.2.1**.

| Sistema | Instalación |
|---|---|
| Windows | Seleccionar Windows y descargar el instalador correspondiente. |
| macOS | Seleccionar macOS y la descarga adecuada al procesador del equipo. |
| Linux | Seleccionar Linux y el paquete compatible con la distribución. |

## Preparar el servidor

Desde la raíz del repositorio, con Python y `uv` instalados, detener cualquier
servidor que utilice la base de demostración y ejecutar:

```bash
uv sync --frozen
uv run python scripts/preparar_pruebas_entrega2.py
uv run python src/manage.py migrate --settings=poki_koa.settings_entregable
uv run python src/manage.py preparar_entregable --settings=poki_koa.settings_entregable --reset
uv run python src/manage.py runserver 127.0.0.1:8000 --settings=poki_koa.settings_entregable --noreload
```

Dejar abierta la terminal del servidor. `--reset` vacía y repone únicamente
`src/db_entregable.sqlite3`; no se debe usar esa base simultáneamente para otras
pruebas. La configuración indicada evita trabajar sobre la base habitual.

El generador actualiza las fechas UTC del entorno y los datos de prueba. Es necesario
regenerarlos si cambia el día UTC, porque la API valida la fecha de nacimiento con
esa referencia. La regeneración no ejecuta las pruebas ni actualiza los reportes
históricos: los resultados nuevos deben exportarse después de una nueva corrida.

## Abrir y ejecutar la colección

1. En Bruno, seleccionar **Open Collection** y abrir la carpeta
   `qa/entrega2/bruno/` del repositorio. No abrir solamente `bruno.json` ni una
   solicitud individual.
2. Seleccionar el entorno **Local**. Su `base_url` debe ser
   `http://127.0.0.1:8000`.
3. Comprobar que aparecen 94 solicitudes numeradas, desde `001-B01` hasta
   `094-M22.v1`. No ejecutar altas individuales antes de la corrida completa.
4. Abrir el menú de la colección y seleccionar **Run**. Ejecutar todas las
   solicitudes, con una iteración, en orden y sin paralelismo.
5. Revisar tanto las solicitudes como sus pruebas. La secuencia es B01–B22
   (pacientes), seguida de M01–M22 (catálogo), con cada verificación `.vN`
   inmediatamente después de su solicitud principal.

Un HTTP 400 o 404 puede ser correcto: las pruebas negativas esperan esos estados.
El resultado se determina por las aserciones, no por exigir HTTP 200 a todas las
solicitudes. Un caso solo se aprueba si pasan todos sus pasos.

Los archivos `.bru` se mantienen compatibles con Bruno; no es necesario migrarlos
para esta entrega. [Referencia oficial del formato](https://docs.usebruno.com/bru-lang/overview).

## Guardar resultados y repetir

En el Runner, seleccionar **Download Report** y guardar el reporte HTML en
`qa/entrega2/`. Conservar el reporte ya entregado; usar un nombre distinto para
una nueva corrida, por ejemplo `resultado-bruno-equipo-02.html`. Anotar responsable,
versión, commit y cambios locales para identificar la ejecución.

Si falla una prueba, conservar el reporte y revisar la solicitud, la respuesta y
la aserción fallida antes de cambiar el código o los datos. Para repetir la colección,
detener el servidor, restablecer la base con el comando anterior y volver a iniciarlo.
**Run Again no restablece los datos**: repetir sin reiniciar el escenario puede
provocar identificadores duplicados, conteos incorrectos o recursos ya eliminados.

La colección se comparte mediante la carpeta completa `qa/entrega2/bruno/`, incluido
el entorno `Local`; el reporte HTML contiene la evidencia de una ejecución.

## Evidencia de esta entrega

La corrida del equipo en Bruno 4.2.1 terminó con 94 solicitudes aprobadas,
0 fallos, 0 omisiones y 265 verificaciones aprobadas.

- [Reporte HTML del equipo](../../qa/entrega2/resultado-bruno-equipo.html).
- [Registro de ejecución](REGISTRO_EJECUCION.md).
- [Matriz de casos](MATRIZ_CASOS.md).
- [Documentación de APIs](DOCUMENTACION_APIS.md).
