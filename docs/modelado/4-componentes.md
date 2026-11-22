# 4. Diagrama de componentes

```mermaid
flowchart TB
    subgraph externos["Sistemas externos"]
      browser["<<externo>> Navegador / usuario clínico"]
      iot["<<externo>> Cuna / monitor IoT"]
      postgres[("<<externo>> PostgreSQL 16")]
      redis[("<<externo>> Redis 7")]
    end

    subgraph pokikoa["Poki Koa"]
      subgraph frontend["Frontend — React + TypeScript"]
        ui["Aplicación React\nPáginas y componentes"]
        frontservices["Servicios frontend\nAxios, mappers y tipos"]
        realtimeclient["Cliente WebSocket\ntiempoReal.ts"]
        ui --> frontservices
        ui --> realtimeclient
      end

      subgraph backend["Backend — Django / ASGI"]
        rest["API REST\nDjango REST Framework"]
        auth["Autenticación y RBAC\nJWT / roles"]
        deviceauth["Autenticación IoT\nX-Device-Api-Key"]
        patients["Dominio patients"]
        devices["Dominio devices"]
        vitals["Dominio vitals"]
        alerts["Dominio alerts"]
        meds["Dominio medications"]
        accounts["Dominio accounts"]
        audit["Dominio audit"]
        reports["Dominio reports"]
        ws["WebSocket\nDjango Channels"]
        channel["Difusión realtime.py"]
      end
    end

    if_rest_prov(("● REST /api/v1\n(provista)"))
    if_rest_req(["☾ REST /api/v1\n(requerida)"])

    if_iot_prov(("● POST telemetry\n(provista)"))
    if_iot_req(["☾ POST telemetry\n(requerida)"])

    if_ws_prov(("● WebSocket /ws/v1\n(provista)"))
    if_ws_req(["☾ WebSocket /ws/v1\n(requerida)"])

    if_sql_prov(("● SQL / ORM\n(provista)"))
    if_sql_req(["☾ SQL / ORM\n(requerida)"])

    if_chan_prov(("● Channel Layer\n(provista)"))
    if_chan_req(["☾ Channel Layer\n(requerida)"])

    rest --- if_rest_prov
    if_rest_prov -.->|consume| if_rest_req
    frontservices --- if_rest_req

    rest --- if_iot_prov
    if_iot_prov -.->|consume| if_iot_req
    iot --- if_iot_req

    ws --- if_ws_prov
    if_ws_prov -.->|consume| if_ws_req
    realtimeclient --- if_ws_req

    postgres --- if_sql_prov
    if_sql_prov -.->|consume| if_sql_req
    patients --- if_sql_req
    devices --- if_sql_req
    vitals --- if_sql_req
    alerts --- if_sql_req
    meds --- if_sql_req
    accounts --- if_sql_req
    audit --- if_sql_req
    reports --- if_sql_req

    redis --- if_chan_prov
    channel --- if_chan_prov
    if_chan_prov -.->|consume| if_chan_req
    ws --- if_chan_req

    browser --> ui
    rest --> auth
    rest --> deviceauth
    deviceauth --> devices
    rest --> patients
    rest --> devices
    rest --> vitals
    rest --> alerts
    rest --> meds
    rest --> accounts
    rest --> audit
    rest --> reports
    vitals --> alerts
    patients --> audit
    devices --> audit
    meds --> audit
    alerts --> audit
    vitals --> channel
    alerts --> channel
```

## Interfaces principales

| Interfaz | Proveedor | Consumidor | Propósito |
|---|---|---|---|
| `REST /api/v1` | Backend DRF | Servicios frontend | Operaciones de pacientes, cunas, signos vitales, alertas, farmacia, turnos y reportes. |
| `POST telemetry` | Backend DRF | Dispositivo IoT | Ingesta autenticada por `X-Device-Api-Key`; también admite personal autenticado según la vista. |
| `WebSocket /ws/v1` | Backend ASGI / Channels | Cliente WebSocket frontend | Eventos de telemetría y alertas con autenticación JWT. |
| `SQL / ORM` | PostgreSQL | Aplicaciones de dominio Django | Persistencia relacional de entidades y trazabilidad. |
| `Channel Layer` | Django Channels con Redis en despliegue | Servicios de difusión y consumidores WebSocket | Enrutamiento de eventos a grupos de unidad, cuna y paciente. |

## Justificación de decisiones

El backend se representa como monolito modular y no como microservicios: los dominios son aplicaciones Django dentro del mismo proceso y comparten transacciones y ORM. El frontend está separado porque es un repositorio y una aplicación React independiente que consume REST y WebSocket. Los dispositivos IoT se muestran como externos y utilizan una interfaz de ingesta autenticada con API Key; los usuarios del navegador consumen la API con sesión/JWT. PostgreSQL representa la persistencia principal y Redis la capa de canales para tiempo real en el despliegue Docker Compose documentado. Los módulos `patients`, `devices`, `vitals`, `alerts`, `medications`, `accounts`, `audit` y `reports` se muestran por separado para reflejar sus límites de dominio y sus responsabilidades. Las interfaces nombradas con puerto provisto y requerido explican el contrato entre capas sin reducir la arquitectura a cajas y flechas sin contrato.

## Componentes externos

- **Navegador:** ejecuta el frontend React.
- **Cuna / monitor IoT:** envía telemetría con API Key propia.
- **PostgreSQL 16:** base de datos relacional.
- **Redis 7:** backend de Channel Layer en la configuración Docker Compose descrita en el README del backend.