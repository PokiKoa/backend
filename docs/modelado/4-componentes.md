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

    restapi(( "REST /api/v1" ))
    wsapi(( "WebSocket /ws/v1" ))
    deviceapi(( "POST telemetry" ))
    sql(( "SQL / ORM" ))
    channelif(( "Channel Layer" ))

    browser --> ui
    frontservices --> restapi
    restapi --> rest
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
    iot --> deviceapi
    deviceapi --> rest
    vitals --> alerts
    patients --> audit
    devices --> audit
    meds --> audit
    alerts --> audit
    vitals --> channel
    alerts --> channel
    channel --> channelif
    channelif --> redis
    channelif --> ws
    realtimeclient --> wsapi
    wsapi --> ws
    ws --> channelif
    patients --> sql
    devices --> sql
    vitals --> sql
    alerts --> sql
    meds --> sql
    accounts --> sql
    audit --> sql
    reports --> sql
    sql --> postgres
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

El backend se representa como monolito modular y no como microservicios: los dominios son aplicaciones Django dentro del mismo proceso y comparten transacciones y ORM. El frontend está separado porque es un repositorio y una aplicación React independiente que consume REST y WebSocket. Los dispositivos IoT se muestran como externos y utilizan una interfaz de ingesta autenticada con API Key; los usuarios del navegador consumen la API con sesión/JWT. PostgreSQL representa la persistencia principal y Redis la capa de canales para tiempo real en el despliegue Docker Compose documentado. Los módulos `patients`, `devices`, `vitals`, `alerts`, `medications`, `accounts`, `audit` y `reports` se muestran por separado para reflejar sus límites de dominio y sus responsabilidades. Los puntos de conexión nombrados evitan reducir la arquitectura a cajas conectadas por flechas sin contrato: cada interfaz indica qué protocolo o servicio ofrece y quién lo consume.

## Componentes externos

- **Navegador:** ejecuta el frontend React.
- **Cuna / monitor IoT:** envía telemetría con API Key propia.
- **PostgreSQL 16:** base de datos relacional.
- **Redis 7:** backend de Channel Layer en la configuración Docker Compose descrita en el README del backend.
