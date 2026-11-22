# 3. Diagrama de secuencia

**Caso elegido:** Enviar telemetría — ingesta de una lectura desde una cuna, validación, evaluación de alertas y publicación en tiempo real.

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
    activate DB
    DB-->>Auth: Fila Crib + api_key_hash + is_device_active
    deactivate DB
    Auth-->>API: DevicePrincipal autenticado (crib_id)
    deactivate Auth

    API->>VitalSvc: ingest_telemetry(crib, payload, is_device_authenticated=true)
    activate VitalSvc
    VitalSvc->>Rules: validate_telemetry_payload(payload)
    activate Rules
    alt Payload inválido
        Rules-->>VitalSvc: Errores de campo / rango fisiológico
        deactivate Rules
        VitalSvc-->>API: DomainError (motivo de rechazo)
        API-->>IoT: HTTP 400 + detalle de validación
    else Payload válido
        Rules-->>VitalSvc: Lectura normalizada válida
        deactivate Rules

        VitalSvc->>DB: BEGIN + SELECT Crib FOR UPDATE
        activate DB
        DB-->>VitalSvc: Crib bloqueada + patient_id actual
        deactivate DB

        VitalSvc->>DB: INSERT VitalSignReading
        activate DB
        DB-->>VitalSvc: VitalSignReading creado (reading_id)
        deactivate DB

        VitalSvc->>DB: UPDATE Crib (last_telemetry_at, status)
        activate DB
        DB-->>VitalSvc: Crib actualizada
        deactivate DB

        VitalSvc->>AlertSvc: evaluate_reading_alerts(reading)
        activate AlertSvc
        AlertSvc->>DB: Leer umbrales efectivos (paciente o globales)
        activate DB
        DB-->>AlertSvc: Umbrales HR, SpO2 y temperatura
        deactivate DB

        AlertSvc->>DB: SELECT alertas abiertas FOR UPDATE
        activate DB
        DB-->>AlertSvc: Alertas activas previas
        deactivate DB

        loop Por cada tipo de anomalía evaluado
            AlertSvc->>AlertSvc: Crear, deduplicar, escalar o autorresolver alerta
        end

        AlertSvc->>DB: INSERT / UPDATE Alert
        activate DB
        DB-->>AlertSvc: Alertas persistidas (activas / resueltas)
        deactivate DB

        AlertSvc-->>VitalSvc: Resumen de evaluación de alertas
        deactivate AlertSvc

        VitalSvc->>DB: COMMIT
        activate DB
        DB-->>VitalSvc: Transacción confirmada
        deactivate DB

        VitalSvc->>WS: broadcast_telemetry_reading(reading, alerts)
        activate WS
        WS-->>UI: Evento telemetry.reading (lectura + alertas)
        WS-->>VitalSvc: Broadcast despachado a grupos
        deactivate WS

        VitalSvc-->>API: (reading, alert_summary)
        deactivate VitalSvc
        API-->>IoT: HTTP 201 + lectura y alertas evaluadas
    end
    deactivate API
```

## Justificación de decisiones

Se escogió **Enviar telemetría** porque es un flujo central y técnicamente representativo: conecta el dispositivo IoT, la autenticación por API Key, la validación fisiológica, la persistencia, el motor de alertas y la interfaz en tiempo real. El flujo sigue `CribViewSet.telemetry` y `ingest_telemetry`; no se modela como si el dispositivo utilizara JWT de usuario. La transacción bloquea la fila de `Crib` para mantener consistentes el paciente asignado, la última marca de telemetría y el estado de la cuna. Después se evalúan umbrales efectivos y se sincronizan las alertas abiertas, incluyendo deduplicación y autorresolución. La difusión se hace después de la evaluación mediante `broadcast_telemetry_reading`, hacia los grupos de unidad, cuna y paciente. El fragmento `alt` distingue un payload inválido de uno aceptado y el `loop` representa la evaluación de los tipos de anomalía; las barras de activación y retornos muestran el control de ejecución y los datos que condicionan cada paso.

## Participantes y responsabilidades

- **Dispositivo IoT:** emite la lectura y presenta la API Key de la cuna.
- **CribViewSet.telemetry:** adapta la petición HTTP, selecciona autenticación y serializa la respuesta.
- **DeviceApiKeyAuthentication:** resuelve y valida la credencial del dispositivo.
- **ingest_telemetry:** coordina validación, persistencia transaccional, evaluación y difusión.
- **vitals.rules:** valida rangos y estructura de la telemetría.
- **PostgreSQL:** persiste lectura, estado de cuna y alertas.
- **evaluate_reading_alerts:** crea, deduplica, escala o autorresuelve alertas.
- **Channels / Frontend:** distribuye y recibe el evento `telemetry.reading`.