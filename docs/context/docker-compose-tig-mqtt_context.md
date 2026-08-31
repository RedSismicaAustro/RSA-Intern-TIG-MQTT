---
proyecto: RSA-Intern-TIG-MQTT
tipo: contexto_tecnico
archivo: services/docker-unified/docker-compose.yml
temas: [docker-compose, telegraf, influxdb, grafana, tig-stack, mqtt, correlator, event-analyzer, db-sync, profiles, rsa_events]
generado: 2026-08-28
---
# Docker Compose Unificado (TIG Stack + MQTT + Correlador + Event Analyzer + DB Sync) — Contexto para Agentes IA

> Orquestación de servicios en un stack Docker unificado (InfluxDB, Telegraf, Grafana, Correlador Regional con perfiles de ejecución, Event Analyzer y utilidades DB Sync) para la recolección, almacenamiento de telemetría y metadatos de eventos sísmicos, análisis en tiempo real, visualización web interactiva y respaldos.

**Ruta**: `services/docker-unified/docker-compose.yml`  
**Rutas de Archivos Asociados**:
- Telegraf Config: `services/docker-unified/telegraf.conf`
- Correlador Regional: `scripts/correlator/`
- Visualizador Web: `services/event-analyzer/`
- Utilidades DB Sync: `scripts/db_sync/`
- Grafana Provisioning: `services/grafana/provisioning/dashboards/` | `datasources/`

**LOC**: `docker-compose.yml`: 196 | `telegraf.conf`: 150  
**Lenguaje/Formato**: YAML (Docker Compose / Provisioning), TOML (Telegraf), JSON (Grafana Dashboards)  
**Dependencias/Imágenes**: `influxdb:2.7`, `telegraf:1.28`, `grafana/grafana:11.2.0`, Python 3.11  
**Proceso**: Stack unificado en contenedores Docker orquestado mediante Docker Compose en la red externa `rsa_network`.

---

## 🎯 Arquitectura del Stack Unificado

El stack coordina 6 servicios integrados con soporte multi-servidor:

1. **InfluxDB (`rsa-influxdb`)**:
   - Gestiona dos buckets: `telemetry` (telemetría y salud con retención de 90 días) y `rsa_events` (metadatos e índice de eventos sísmicos con retención infinita).
2. **Telegraf (`rsa-telegraf`)**:
   - Ingesta métricas de salud en `telemetry` y metadatos JSON con QoS 1 en `rsa_events`.
3. **Grafana (`rsa-grafana`)**:
   - Visualización de telemetría y salud mediante dashboards provisionados.
4. **Correlador Regional (`rsa-correlator`)**:
   - Aislado bajo `profiles: ["primary"]` para ejecución exclusiva en el servidor principal (`rsa-server`). Usa sesión persistente MQTT.
5. **Event Analyzer (`rsa-event-analyzer`)**:
   - Aplicación web en Streamlit (:8501) y Dash (:8050) para visualización multi-estación y clasificación.
6. **DB Sync (`rsa-db-sync`)**:
   - Contenedor utilitario bajo demanda (sin `restart`) para notificación de respaldos y scripts de mantenimiento.

```mermaid
graph TD
    Broker[Mosquitto Broker: 174.138.41.251] -->|MQTT 1883| Telegraf[Telegraf: rsa-telegraf]
    Broker -->|events/detected| Correlator[Correlator (Profile: primary)]
    Correlator -->|events/metadata QoS 1| Broker

    subgraph InfluxDB Buckets
        Telegraf -->|telemetry| B1[(Bucket: telemetry)]
        Telegraf -->|rsa_events| B2[(Bucket: rsa_events)]
    end

    Grafana[Grafana :3000] -->|Consulta Flux| B1
    Analyzer[Event Analyzer :8501] -->|Consulta Flux & Clasificacion| B2
    Analyzer -->|Publicacion QoS 1| Broker
    DBSync[DB Sync (Bajo demanda)] -->|backup QoS 1| Broker
```

---

## ⚙️ Variables de Entorno Clave (`.env`)

- `DATA_DIR=/home/rsa/data`: Ruta base para persistencia.
- `DRIVE_DIR=/home/rsa/datos_estaciones_drive`: Punto de montaje MiniSEED.
- `INFLUXDB_BUCKET=telemetry`: Bucket de series temporales.
- `INFLUXDB_EVENTS_BUCKET=rsa_events`: Bucket de metadatos de eventos.
- `TELEGRAF_CLIENT_ID=events-oficina`: ID del servidor para Telegraf y backups.
- `RSA_SERVER_ROLE=primary`: Rol del servidor (`primary` vs `mirror`).
- `RSA_CORRELATOR_CLIENT_ID=rsa-correlator-primary`: Client ID fijo para sesión persistente.
- `RCLONE_REMOTE="gdrive:DIA/Datos Estaciones/RSA-Backups/influxdb"`: Destino de respaldos en Google Drive.

---

## 🐳 Servicios Definidos en `docker-compose.yml`

| Servicio | Contenedor | Perfil | Puerto | Propósito |
|----------|------------|--------|--------|-----------|
| `influxdb` | `rsa-influxdb` | *(default)* | 8086 | Base de datos de telemetría y eventos. |
| `telegraf` | `rsa-telegraf` | *(default)* | - | Ingesta dual segmentada (telemetry / rsa_events). |
| `grafana` | `rsa-grafana` | *(default)* | 3000 | Dashboards de salud de estaciones. |
| `correlator` | `rsa-correlator` | `primary` | - | Validación regional y disparo broadcast (solo en primary). |
| `event-analyzer` | `rsa-event-analyzer` | *(default)* | 8501, 8050 | Visualizador web y clasificador interactivo. |
| `db-sync` | `rsa-db-sync` | *(default)* | - | Utilidades bajo demanda para notificación MQTT y scripts. |
