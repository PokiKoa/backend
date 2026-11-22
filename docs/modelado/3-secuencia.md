# 3. Diagrama de secuencia

**Caso de uso modelado:** *CU-23 Registrar telemetría* (diagrama de casos de uso, actor *Cuna con monitor*). Incluye *CU-24 Validar rangos fisiológicos* y, cuando la lectura sale de los umbrales, se extiende con *CU-25 Generar alerta clínica*. Es el flujo más completo del sistema: va desde la cuna hasta la pantalla del personal.

```mermaid
sequenceDiagram
    autonumber
    participant IoT as Cuna con monitor (IoT)
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
    DB-->>Auth: Crib + api_key_hash + is_device_active + status
    deactivate DB
    Auth-->>API: (DevicePrincipal, Crib) o AuthenticationFailed
    deactivate Auth

    alt API Key inválida, dispositivo deshabilitado o cuna en mantenimiento
        API-->>IoT: HTTP 401 Unauthorized
    else API Key válida
        API->>VitalSvc: ingest_telemetry(crib, payload, is_device_authenticated=true)
        activate VitalSvc
        VitalSvc->>Rules: validate_telemetry_payload(payload)
        activate Rules
        Rules-->>VitalSvc: Lectura normalizada o errores de rango fisiológico
        deactivate Rules

        alt Payload inválido (CU-24)
            VitalSvc-->>API: DomainError con el motivo del rechazo
            API-->>IoT: HTTP 400 + detalle de validación
        else Payload válido
            VitalSvc->>DB: BEGIN + SELECT Crib FOR UPDATE
            activate DB
            DB-->>VitalSvc: Crib bloqueada + paciente actual
            deactivate DB

            alt Cuna en mantenimiento o dispositivo deshabilitado
                VitalSvc-->>API: ConflictDomainError (ROLLBACK)
                API-->>IoT: HTTP 409 Conflict
            else Cuna operativa
                VitalSvc->>DB: INSERT VitalSignReading
                activate DB
                DB-->>VitalSvc: Lectura creada (reading_id)
                deactivate DB

                VitalSvc->>DB: UPDATE Crib (last_telemetry_at, status)
                activate DB
                DB-->>VitalSvc: Cuna actualizada
                deactivate DB

                VitalSvc->>AlertSvc: evaluate_reading_alerts(reading)
                activate AlertSvc
                AlertSvc->>DB: Leer umbrales efectivos (del paciente o globales)
                activate DB
                DB-->>AlertSvc: Umbrales de FC, SpO2 y temperatura
                deactivate DB

                AlertSvc->>DB: SELECT alertas abiertas FOR UPDATE
                activate DB
                DB-->>AlertSvc: Alertas abiertas de la cuna
                deactivate DB

                loop Por cada tipo de anomalía evaluado (CU-25)
                    AlertSvc->>AlertSvc: Crear, deduplicar, escalar o autorresolver la alerta
                end

                AlertSvc->>DB: INSERT / UPDATE Alert
                activate DB
                DB-->>AlertSvc: Alertas activas y autorresueltas
                deactivate DB
                AlertSvc-->>VitalSvc: Resumen de la evaluación
                deactivate AlertSvc

                VitalSvc->>DB: COMMIT
                activate DB
                DB-->>VitalSvc: Transacción confirmada
                deactivate DB

                VitalSvc->>WS: broadcast_telemetry_reading(lectura, alertas)
                activate WS
                WS-->>UI: Evento telemetry.reading (unidad, cuna y paciente)
                deactivate WS

                VitalSvc-->>API: (lectura, resumen de alertas)
                API-->>IoT: HTTP 201 + lectura y alertas evaluadas
            end
        end
        deactivate VitalSvc
    end
    deactivate API
```

## Justificación de decisiones

Se modeló *Registrar telemetría* porque atraviesa todas las capas del sistema: la cuna se autentica con su API Key (no con JWT de usuario), se validan los rangos fisiológicos, se persiste la lectura en una transacción, se evalúan las alertas y el resultado llega en tiempo real a la interfaz. La transacción bloquea la fila de `Crib` para que el paciente asignado, la última marca de telemetría y el estado de la cuna se mantengan consistentes aunque lleguen lecturas simultáneas. La difusión por Channels ocurre **después** del `COMMIT`, de modo que ningún cliente recibe una lectura que luego se revierta. Los tres fragmentos `alt` muestran los rechazos reales del código (401 de la autenticación, 400 de la validación y 409 si la cuna está en mantenimiento o deshabilitada), y el `loop` representa la evaluación de cada tipo de alerta, que puede crear, deduplicar, escalar o autorresolver. Se muestran solo los retornos que cambian el paso siguiente; `broadcast_telemetry_reading` no devuelve nada, por eso no tiene retorno.

## Participantes y responsabilidades

- **Cuna con monitor (IoT):** actor externo; emite la lectura y presenta la API Key de la cuna.
- **CribViewSet.telemetry:** adapta la petición HTTP, elige la autenticación y arma la respuesta (`src/devices/views.py`).
- **DeviceApiKeyAuthentication:** resuelve la cuna por el prefijo de la clave y verifica el hash (`src/devices/authentication.py`).
- **ingest_telemetry:** coordina validación, transacción, evaluación y difusión (`src/vitals/services.py`).
- **vitals.rules:** valida estructura y rangos fisiológicos (`src/vitals/rules.py`).
- **PostgreSQL:** persiste lectura, estado de la cuna y alertas.
- **evaluate_reading_alerts:** crea, deduplica, escala o autorresuelve alertas (`src/alerts/services.py`).
- **vitals.realtime / Channels y Frontend React:** distribuyen y reciben el evento `telemetry.reading` (`src/vitals/realtime.py`, `frontend/src/api/tiempoReal.ts`).
