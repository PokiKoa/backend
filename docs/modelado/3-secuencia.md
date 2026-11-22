# 3. Diagrama de secuencia

**Caso elegido:** ingesta de una lectura de telemetría desde una cuna, evaluación de alertas y publicación en tiempo real.

```mermaid
sequenceDiagram
    autonumber
    participant IoT as Dispositivo IoT
    participant API as CribViewSet.telemetry
    participant Auth as DeviceApiKeyAuthentication
    participant VitalSvc as vitals.services.ingest_telemetry
    participant Rules as vitals.rules
    participant DB as PostgreSQL
    participant AlertSvc as alerts.services.evaluate_reading_alerts
    participant WS as vitals.realtime / Channels
    participant UI as Frontend React

    IoT->>API: POST /api/v1/cribs/{id}/telemetry + X-Device-Api-Key
    activate API
    API->>Auth: authenticate(request)
    activate Auth
    Auth->>DB: Buscar Crib por api_key_prefix
    DB-->>Auth: Crib y hash almacenado
    Auth-->>API: DevicePrincipal autenticado
    deactivate Auth

    API->>VitalSvc: ingest_telemetry(crib, payload, is_device_authenticated=true)
    activate VitalSvc
    VitalSvc->>Rules: validate_telemetry_payload(payload)
    activate Rules
    alt Payload inválido
        Rules-->>VitalSvc: Error de validación
        VitalSvc-->>API: DomainError
        API-->>IoT: Respuesta de error
    else Payload válido
        Rules-->>VitalSvc: Lectura validada
        deactivate Rules
        VitalSvc->>DB: BEGIN + SELECT Crib FOR UPDATE
        DB-->>VitalSvc: Cuna bloqueada y paciente actual
        VitalSvc->>DB: INSERT VitalSignReading
        VitalSvc->>DB: UPDATE Crib.last_telemetry_at / status
        VitalSvc->>AlertSvc: evaluate_reading_alerts(reading)
        activate AlertSvc
        AlertSvc->>DB: Leer umbrales efectivos
        DB-->>AlertSvc: Umbrales globales o del paciente
        AlertSvc->>DB: SELECT alertas abiertas FOR UPDATE
        DB-->>AlertSvc: Alertas existentes
        loop Por cada tipo de anomalía evaluado
            AlertSvc->>AlertSvc: Crear, deduplicar, escalar o autorresolver
        end
        AlertSvc->>DB: INSERT / UPDATE Alert
        AlertSvc-->>VitalSvc: Resumen de alertas
        deactivate AlertSvc
        VitalSvc->>DB: COMMIT
        VitalSvc->>WS: broadcast_telemetry_reading(...)
        activate WS
        WS-->>UI: telemetry.reading (lectura + alertas activas/resueltas)
        deactivate WS
        VitalSvc-->>API: (reading, evaluation)
        API-->>IoT: HTTP 201 + lectura y alertas
    end
    deactivate VitalSvc
    deactivate API
```

## Justificación de decisiones

Se escogió la telemetría porque es un flujo central y técnicamente representativo: conecta el dispositivo IoT, la autenticación por API Key, la validación fisiológica, la persistencia, el motor de alertas y la interfaz en tiempo real. El flujo sigue `CribViewSet.telemetry` y `ingest_telemetry`; no se modela como si el dispositivo utilizara JWT de usuario. La transacción bloquea la fila de `Crib` para mantener consistentes el paciente asignado, la última marca de telemetría y el estado de la cuna. Después se evalúan umbrales efectivos y se sincronizan las alertas abiertas, incluyendo deduplicación y autorresolución. La difusión se hace después de la evaluación mediante `broadcast_telemetry_reading`, hacia los grupos de unidad, cuna y paciente. El fragmento `alt` distingue un payload inválido de uno aceptado y el `loop` representa la evaluación de los tipos de anomalía; los retornos muestran resultados que cambian el paso siguiente.

## Participantes y responsabilidades

- **Dispositivo IoT:** emite la lectura y presenta la API Key de la cuna.
- **CribViewSet.telemetry:** adapta la petición HTTP, selecciona autenticación y serializa la respuesta.
- **DeviceApiKeyAuthentication:** resuelve y valida la credencial del dispositivo.
- **ingest_telemetry:** coordina validación, persistencia transaccional, evaluación y difusión.
- **vitals.rules:** valida rangos y estructura de la telemetría.
- **PostgreSQL:** persiste lectura, estado de cuna y alertas.
- **evaluate_reading_alerts:** crea, deduplica, escala o autorresuelve alertas.
- **Channels / Frontend:** distribuye y recibe el evento `telemetry.reading`.
