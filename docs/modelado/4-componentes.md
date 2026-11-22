# 4. Diagrama de componentes

En qué piezas se divide Poki Koa cuando se despliega con `docker-compose.prod.yml` y qué interfaces las conectan. Cada componente corresponde a una carpeta de este repositorio, a una carpeta de [PokiKoa/frontend](https://github.com/PokiKoa/frontend) o a un servicio del archivo de despliegue.

```mermaid
flowchart TB
    NAV["«actor»<br/>Navegador del personal"]
    CUNA["«componente externo»<br/>Cuna con monitor"]

    I_HTTPS(("HTTPS"))
    I_TEL(("Telemetría<br/>X-Device-Api-Key"))

    CADDY["«componente externo»<br/>Caddy · proxy TLS"]

    I_SPA(("Archivos<br/>de la SPA"))
    I_REST(("REST<br/>/api/v1"))
    I_WS(("WebSocket<br/>/ws/v1"))

    subgraph FE["«componente» Frontend SPA"]
        NGINX["nginx<br/>dist/ · docker/nginx.conf"]
        FEUI["pages/<br/>MapaCunasPage, …"]
        FEAPI["api/<br/>axios.ts · tiempoReal.ts"]
    end

    subgraph BE["«componente» Backend Poki Koa (servicio app)"]
        CORE["poki_koa<br/>urls · asgi"]
        DEV["devices"]
        VIT["vitals"]
        ALR["alerts"]
        PAT["patients"]
        MED["medications"]
        ACC["accounts"]
        AUD["audit"]
        REP["reports"]
        ORM["ORM de Django<br/>models.py de cada app"]
    end

    I_ING(("ingest_telemetry()"))
    I_EVA(("evaluate_reading_alerts()"))
    I_AUD(("record_audit_event()"))

    MON["«componente»<br/>offline-monitor<br/>check_offline_cribs"]

    I_SQL(("SQL"))
    I_CH(("Channel layer<br/>group_send"))

    DB[("«componente externo»<br/>«persistencia»<br/>PostgreSQL 16")]
    RDS[("«componente externo»<br/>Redis 7<br/>capa de canales")]

    %% Interfaces requeridas (enchufe): flecha punteada «use» hacia la interfaz
    NAV -.->|«use»| I_HTTPS
    CUNA -.->|«use»| I_TEL
    CADDY -.->|«use»| I_SPA
    CADDY -.->|«use»| I_REST
    CADDY -.->|«use»| I_WS
    FEUI ~~~ FEAPI
    FEAPI -.->|«use»| I_REST
    FEAPI -.->|«use»| I_WS
    DEV -.->|«use»| I_ING
    VIT -.->|«use»| I_EVA
    PAT -.->|«use»| I_AUD
    MED -.->|«use»| I_AUD
    ORM -.->|«use»| I_SQL
    VIT -.->|«use»| I_CH
    MON -.->|«use»| I_SQL
    MON -.->|«use»| I_CH

    %% Interfaces provistas (bola): línea continua hacia quien la ofrece
    I_HTTPS --- CADDY
    I_TEL --- DEV
    I_SPA --- NGINX
    I_REST --- CORE
    I_WS --- VIT
    I_ING --- VIT
    I_EVA --- ALR
    I_AUD --- AUD
    I_SQL --- DB
    I_CH --- RDS
```

**Cómo leerlo.** Mermaid no tiene un tipo de diagrama de componentes, así que se representa con un diagrama de flujo:

- Cada recuadro es un componente. Los recuadros grandes (*Frontend SPA*, *Backend Poki Koa*) contienen sus módulos internos.
- Cada círculo es una **interfaz con nombre**. La línea continua sale del componente que la **provee** (la bola).
- La flecha punteada `«use»` sale de cada componente que la **requiere** (el enchufe).
- `«componente externo»` marca software que el equipo no escribió: la cuna, Caddy, PostgreSQL y Redis.
- La persistencia es PostgreSQL, el único componente con estado clínico. Dentro del backend, el ORM de Django (los `models.py` de cada aplicación) es el único que habla SQL.
- Todo corre en el servidor de cada centro con Docker, salvo el navegador y la cuna.
- Para no recargar el dibujo, solo dos aplicaciones de dominio aparecen usando `record_audit_event()`. En el código la llaman todos los servicios que modifican datos: `accounts`, `devices`, `patients`, `alerts` y `medications`.
