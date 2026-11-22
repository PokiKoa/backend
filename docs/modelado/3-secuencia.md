# 3. Diagrama de secuencia: Registrar telemetría

Caso de uso **CU-23 Registrar telemetría** del [diagrama de casos de uso](1-casos-de-uso.md): una cuna envía una lectura de signos vitales, el backend la valida y la guarda, evalúa las alertas y la difunde en tiempo real al mapa de cunas.

```mermaid
sequenceDiagram
    autonumber
    participant CUNA as Cuna con monitor<br/>«sistema externo»
    participant VIEW as CribViewSet.telemetry<br/>(devices.views)
    participant AUTH as DeviceApiKeyAuthentication<br/>(devices.authentication)
    participant SVC as ingest_telemetry<br/>(vitals.services)
    participant RULES as validate_telemetry_payload<br/>(vitals.rules)
    participant ALR as evaluate_reading_alerts<br/>(alerts.services)
    participant DB as PostgreSQL
    participant RT as Capa de canales<br/>(vitals.realtime + Redis)
    participant WS as TelemetryAlertConsumer<br/>(vitals.consumers)
    participant FE as MapaCunasPage<br/>(frontend)

    CUNA->>VIEW: POST /api/v1/cribs/{id}/telemetry/<br/>X-Device-Api-Key + lectura JSON
    activate VIEW
    VIEW->>+AUTH: authenticate(request)
    AUTH->>DB: SELECT Crib por api_key_prefix
    DB-->>AUTH: Crib + api_key_hash
    AUTH-->>-VIEW: DevicePrincipal(crib) o AuthenticationFailed

    alt API Key inválida o de otra cuna
        VIEW-->>CUNA: 403 {"error": ...}
    else credencial válida para esta cuna
        VIEW->>+SVC: ingest_telemetry(crib, payload, is_device_authenticated=True)
        SVC->>+RULES: validate_telemetry_payload(payload)
        RULES-->>-SVC: ValidatedTelemetryPayload
        Note over SVC,RULES: Si un valor está fuera del rango fisiológico<br/>(p. ej. heart_rate = 900) responde 400 y no guarda nada

        SVC->>DB: BEGIN · SELECT Crib FOR UPDATE
        SVC->>DB: INSERT VitalSignReading (patient = paciente actual de la cuna)
        opt la cuna estaba offline
            SVC->>DB: UPDATE Crib.status = occupied o available
        end

        SVC->>+ALR: evaluate_reading_alerts(reading)
        ALR->>DB: SELECT AlertThresholdConfig del paciente (o la global)
        DB-->>ALR: umbrales vigentes
        ALR->>ALR: evaluate_vital_reading(reading, umbrales)
        loop cada tipo evaluado: heart_rate, spo2, temperature, cannula, sensor_fault
            alt anomalía con alerta abierta de la misma severidad
                ALR->>DB: UPDATE Alert: occurrence_count + 1 (deduplica)
            else anomalía sin alerta abierta equivalente
                ALR->>DB: INSERT Alert (status = active)
            else sin anomalía y con alerta abierta
                ALR->>DB: UPDATE Alert: resolved (auto_normalized)
            end
        end
        ALR-->>-SVC: AlertEvaluationSummary (activas y autorresueltas)
        SVC->>DB: COMMIT

        SVC->>+RT: broadcast_telemetry_reading(lectura, alertas)
        RT->>WS: group_send a unidad, cuna y paciente
        deactivate RT
        activate WS
        WS->>FE: evento telemetry.reading (JSON)
        deactivate WS
        activate FE
        FE->>FE: aplicarEventoCunas() y repinta la cuna con su alerta
        deactivate FE

        SVC-->>-VIEW: (reading, evaluation)
        VIEW->>VIEW: serializa la lectura y las alertas para la respuesta
        VIEW-->>CUNA: 201 Created + active_alerts + auto_resolved_alerts
    end
    deactivate VIEW
```

**Cómo leerlo.**

- La numeración automática permite citar cada mensaje en la presentación ("el mensaje 24 es la alerta que llega a la pantalla").
- Solo se dibujan los retornos que traen información. `broadcast_telemetry_reading` y `group_send` no devuelven nada útil, así que no tienen flecha de vuelta.
- En el `alt` de las alertas falta un caso, para no recargar el dibujo: si la severidad cambia (de advertencia a crítica), la alerta anterior se cierra como `severity_escalated` y se crea una nueva.

## Correspondencia con el código

| Línea de vida | Dónde está |
|---|---|
| Cuna con monitor | Actor externo de CU-23. En desarrollo lo reemplaza `simulate_telemetry` |
| `CribViewSet.telemetry` | `src/devices/views.py`, acción `telemetry` (`POST`) |
| `DeviceApiKeyAuthentication` | `src/devices/authentication.py`, cabecera `X-Device-Api-Key` |
| `ingest_telemetry` | `src/vitals/services.py` |
| `validate_telemetry_payload` | `src/vitals/rules.py` (fuente única de los rangos fisiológicos) |
| `evaluate_reading_alerts` | `src/alerts/services.py`, con `evaluate_vital_reading` de `src/alerts/policies.py` |
| Capa de canales | `src/vitals/realtime.py` (`broadcast_telemetry_reading`), Redis en producción |
| `TelemetryAlertConsumer` | `src/vitals/consumers.py`, ruta `ws/v1/monitoring/stream/` |
| `MapaCunasPage` | Frontend: `src/pages/mapa/MapaCunasPage.tsx` y `aplicarEventoCunas` en `src/services/cunasService.ts` |
