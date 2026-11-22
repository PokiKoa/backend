# 2. Diagrama de clases

```mermaid
classDiagram
direction LR

class User {
  +int id
  +string username
  +string email
  +string full_name
  +string role
  +string shift
  +bool is_active
  +bool is_two_factor_enabled
  +datetime created_at
  +datetime updated_at
}

class Patient {
  +int id
  +string medical_record_number
  +string full_name
  +string sex
  +date birth_date
  +decimal gestational_age_weeks
  +int birth_weight_g
  +int current_weight_g
  +datetime admitted_at
  +string diagnosis
  +string status
  +datetime discharged_at
  +string discharge_outcome
  +string discharge_cause
  +int age_days
}

class Crib {
  +int id
  +string code
  +string name
  +string location
  +string status
  +string api_key_prefix
  +string api_key_hash
  +bool is_device_active
  +datetime last_telemetry_at
}

class VitalSignReading {
  +int id
  +int heart_rate
  +int spo2
  +decimal temperature
  +string sleep_state
  +bool cannula_connected
  +bool iv_line_active
  +datetime recorded_at
  +datetime ingested_at
}

class Alert {
  +int id
  +string alert_type
  +string severity
  +string status
  +string message
  +decimal measured_value
  +decimal threshold_value
  +int occurrence_count
  +datetime triggered_at
  +datetime acknowledged_at
  +datetime resolved_at
  +string resolution_reason
}

class AlertThresholdConfig {
  +int id
  +int heart_rate_critical_low
  +int heart_rate_warning_low
  +int heart_rate_warning_high
  +int heart_rate_critical_high
  +int spo2_critical_low
  +int spo2_warning_low
  +decimal temp_critical_low
  +decimal temp_warning_low
  +decimal temp_warning_high
  +decimal temp_critical_high
  +datetime updated_at
}

class MedicationCatalogItem {
  +int id
  +string name
  +string active_ingredient
  +decimal concentration_mg
  +string unit
  +int stock
  +int min_stock_alert
  +bool is_active
}

class Prescription {
  +int id
  +string dose
  +decimal units_per_administration
  +string route
  +datetime starts_at
  +int frequency_hours
  +datetime ends_at
  +string status
}

class MedicationAdministration {
  +int id
  +datetime scheduled_for
  +datetime administered_at
  +string notes
}

class WeightRecord {
  +int id
  +int weight_g
  +datetime recorded_at
}

class CarePlan {
  +int id
  +string care_area
  +string intervention
  +string frequency
  +string status
  +datetime created_at
}

class ClinicalObservation {
  +int id
  +string category
  +string content
  +datetime created_at
}

class CribMovement {
  +int id
  +string kind
  +string from_crib_code
  +string to_crib_code
  +datetime moved_at
}

class ShiftAssignment {
  +int id
  +date date
  +string shift
  +datetime created_at
}

class AuditLog {
  +int id
  +string actor_device_code
  +int patient_id
  +string action
  +string resource_type
  +string resource_id
  +json changed_fields
  +string ip_address
  +datetime timestamp
}

User "1" --> "0..*" Patient : attending_physician
User "1" --> "0..*" Patient : discharged_by
Crib "0..1" <-- "0..1" Patient : current crib
Crib "1" --> "0..*" VitalSignReading : emits
Patient "0..1" <-- "0..*" VitalSignReading : recorded for
Crib "1" --> "0..*" Alert : triggers
Patient "0..1" <-- "0..*" Alert : experiences
Patient "1" --> "0..1" AlertThresholdConfig : custom thresholds
User "0..1" --> "0..*" Alert : acknowledges
User "0..1" --> "0..*" Alert : resolves
MedicationCatalogItem "1" --> "0..*" Prescription : supplies
Patient "1" --> "0..*" Prescription : receives
User "1" --> "0..*" Prescription : prescribes
Prescription "1" *-- "0..*" MedicationAdministration : administrations
User "0..1" --> "0..*" MedicationAdministration : administers
Patient "1" --> "0..*" WeightRecord : weight history
User "0..1" --> "0..*" WeightRecord : records
Patient "1" --> "0..*" CarePlan : care plans
User "1" --> "0..*" CarePlan : creates
Patient "1" --> "0..*" ClinicalObservation : observations
User "1" --> "0..*" ClinicalObservation : authors
Patient "1" --> "0..*" CribMovement : movement history
User "0..1" --> "0..*" CribMovement : moves
User "1" --> "0..*" ShiftAssignment : assigned user
Crib "1" --> "0..*" ShiftAssignment : staffed crib
User "1" --> "0..*" ShiftAssignment : created_by
User "0..1" --> "0..*" AuditLog : actor
```

## Justificación de decisiones

Se modelan las entidades persistentes que definen el dominio clínico y operativo, manteniendo los nombres usados en los modelos Django. `Patient` se conecta con sus lecturas, alertas, historial ponderal, planes, observaciones, prescripciones y movimientos de cuna porque el código conserva la trazabilidad por paciente. `Crib` tiene como máximo un paciente actual mediante `OneToOneField`, aunque conserva muchas lecturas y alertas históricas. Las multiplicidades opcionales reflejan las claves foráneas anulables, por ejemplo `VitalSignReading.patient`, `Alert.patient` y `AlertThresholdConfig.patient`. La composición entre `Prescription` y `MedicationAdministration` representa que cada administración pertenece a una prescripción y su ciclo de vida se gestiona desde ella; confirmar el detalle de borrado físico requiere revisar la política de retención de datos antes de cambiarla. `AuditLog` conserva actor y recurso, pero su campo `patient_id` es un identificador escalar y no una FK de Django; por eso no se dibuja como asociación formal a `Patient`. `age_days` se incluye como propiedad calculada, no como columna persistida.

## Criterios de lectura

- `+` indica visibilidad pública en la representación UML.
- Los tipos corresponden a tipos conceptuales de los campos Django; `datetime`, `date`, `decimal`, `json` e `int` resumen sus tipos persistidos.
- `0..1` indica una relación opcional o única; `0..*` indica colección histórica.
- Las clases de vistas, serializers, servicios y componentes React se describen en el diagrama de componentes, no como entidades de dominio.
