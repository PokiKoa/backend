# 1. Diagrama de casos de uso

```mermaid
flowchart LR
    admin["Administrador"]
    neo["Neonatólogo"]
    nurse["Matrona / Enfermera"]
    pharma["Químico Farmacéutico"]
    iot["Dispositivo IoT de cuna"]

    subgraph sistema["Poki Koa — Plataforma de monitoreo neonatal"]
      auth(["Autenticarse"])
      dashboard(["Consultar panel de la unidad"])
      patients(["Gestionar ficha y egreso de pacientes"])
      crib(["Asignar, liberar o intercambiar cunas"])
      vitals(["Consultar historial de signos vitales"])
      plans(["Gestionar planes y observaciones clínicas"])
      thresholds(["Configurar umbrales clínicos"])
      alerts(["Consultar, reconocer y resolver alertas"])
      prescriptions(["Crear y gestionar prescripciones"])
      administer(["Registrar administración de dosis"])
      catalog(["Mantener catálogo y stock de medicamentos"])
      shifts(["Gestionar turnos y asignaciones"])
      devices(["Administrar cunas y credenciales IoT"])
      reports(["Generar reportes"])
      audit(["Consultar auditoría"])
      telemetry(["Enviar telemetría"])
      evaluate(["Validar lectura y evaluar alertas"])
      broadcast(["Publicar evento en tiempo real"])
    end

    admin --> auth
    neo --> auth
    nurse --> auth
    pharma --> auth
    admin --> dashboard
    neo --> dashboard
    nurse --> dashboard
    admin --> patients
    neo --> patients
    nurse --> patients
    admin --> crib
    neo --> crib
    nurse --> crib
    neo --> plans
    nurse --> plans
    admin --> plans
    neo --> thresholds
    admin --> thresholds
    admin --> alerts
    neo --> alerts
    nurse --> alerts
    admin --> prescriptions
    neo --> prescriptions
    pharma --> prescriptions
    nurse --> administer
    neo --> administer
    pharma --> catalog
    admin --> catalog
    admin --> shifts
    admin --> devices
    admin --> reports
    neo --> reports
    nurse --> reports
    admin --> audit
    iot --> telemetry
    nurse --> vitals
    neo --> vitals
    admin --> vitals

    patients -.->|"<<include>>"| auth
    crib -.->|"<<include>>"| auth
    plans -.->|"<<include>>"| auth
    alerts -.->|"<<include>>"| auth
    prescriptions -.->|"<<include>>"| auth
    administer -.->|"<<include>>"| auth
    catalog -.->|"<<include>>"| auth
    telemetry -.->|"<<include>>"| evaluate
    evaluate -.->|"<<include>>"| broadcast
    alerts -.->|"<<include>>"| audit
    patients -.->|"<<include>>"| audit
    devices -.->|"<<include>>"| audit
```

## Justificación de decisiones

La frontera agrupa las funciones implementadas por Poki Koa, mientras que los perfiles clínicos y administrativos se separan porque el backend aplica permisos RBAC por rol. El dispositivo IoT aparece como actor independiente: no inicia sesión como profesional, sino que envía telemetría autenticándose mediante `X-Device-Api-Key`. Se eligió mostrar la gestión clínica del paciente, las cunas, los signos vitales, las alertas, los medicamentos, los turnos, los reportes y la auditoría para cubrir los módulos presentes en ambos repositorios. La relación `include` hacia autenticación representa que las operaciones de la interfaz protegida requieren una sesión; el envío de telemetría incluye validación/evaluación y difusión de eventos según `vitals.services.ingest_telemetry`. La auditoría se incluye en operaciones sensibles porque los servicios de dominio registran los cambios sin guardar valores clínicos. Las funciones específicas de administración de credenciales y configuración se asignan al administrador, coherente con los permisos de las vistas y servicios.

## Alcance por actor

- **Administrador:** cuentas y roles, configuración de cunas y claves, turnos, umbrales globales, auditoría, reportes y operaciones clínicas permitidas.
- **Neonatólogo:** pacientes, planes/observaciones, umbrales, alertas, signos vitales, prescripciones y seguimiento clínico.
- **Matrona / Enfermera:** pacientes, asignación/liberación de cunas, observaciones, signos vitales, alertas y administración de dosis según permisos del servicio.
- **Químico Farmacéutico:** catálogo, stock y funciones de farmacia expuestas por el frontend y API.
- **Dispositivo IoT:** ingesta de telemetría para la cuna asociada a su API Key.

> Nota: el diagrama agrupa acciones relacionadas en casos de uso de nivel funcional. No afirma que cada rol tenga acceso irrestricto a todas las acciones dentro de un caso agrupado; la autorización fina se mantiene en `accounts/roles.py`, permisos DRF y servicios.