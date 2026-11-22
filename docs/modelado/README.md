# Modelado del sistema Poki Koa

Cuatro diagramas UML que describen el sistema **tal como está construido** en este repositorio y en [PokiKoa/frontend](https://github.com/PokiKoa/frontend). Están escritos como código Mermaid dentro de cada archivo, así que GitHub los dibuja solo y cualquier cambio se revisa en el mismo pull request.

| # | Diagrama | Qué responde |
|---|---|---|
| 1 | [Casos de uso](1-casos-de-uso.md) | Quién usa el sistema (los cuatro roles, la cuna con monitor y el temporizador) y qué puede hacer cada uno |
| 2 | [Clases](2-clases.md) | Los modelos de Django de cada aplicación, con sus atributos, relaciones y multiplicidades |
| 3 | [Secuencia](3-secuencia.md) | Cómo se resuelve *Registrar telemetría*, mensaje por mensaje, desde la cuna hasta la pantalla |
| 4 | [Componentes](4-componentes.md) | En qué piezas se divide el sistema y qué interfaces las conectan |

## Nota de lectura

Los cuatro diagramas son un solo modelo: un mismo concepto se llama igual en todos y en el código. La forma de comprobarlo es seguir un concepto de punta a punta:

- **La alerta.** En casos de uso es *CU-25 Generar alerta clínica* y *CU-17 Reconocer o resolver alerta*. En clases es `Alert`, que se evalúa con los umbrales de `AlertThresholdConfig` (la composición de `Patient`). En la secuencia la crea, deduplica o resuelve `evaluate_reading_alerts` (mensajes 20 a 28). En el código vive en `src/alerts/`.
- **La cuna.** En casos de uso es el actor externo *Cuna con monitor*. En clases es `Crib`. En la secuencia es la primera línea de vida, autenticada con `X-Device-Api-Key`, y en componentes es la *Cuna / monitor IoT* externa que consume la interfaz `POST telemetry`. En el código vive en `src/devices/`.
- **El temporizador.** En casos de uso es el actor *Temporizador (cada 60 s)* de *CU-26 Detectar cunas desconectadas*. En componentes es el externo *Temporizador* que dispara `offline-monitor`. En el código es el servicio `offline-monitor` del `docker-compose.yml` y el comando `check_offline_cribs`.

Elegimos diagramas como código, y no imágenes, porque así el modelo evoluciona junto al sistema. Si un modelo, una regla de permisos o un servicio cambia, el diagrama se corrige en el mismo PR y la diferencia queda en el historial.
