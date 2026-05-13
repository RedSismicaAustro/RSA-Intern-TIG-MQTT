# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Project Overview

Real-time monitoring dashboard for the **Red Sísmica del Austro (RSA)** seismic network. This system uses the **TIG stack (Telegraf, InfluxDB, Grafana)** with **MQTT integration** to collect, store, and visualize telemetry metrics from distributed accelerograph stations.

**Project Status**: 100% complete — DELIVERED. Core components (Docker services, Telegraf config, Grafana provisioning) are implemented, tested, and validated. The system runs as a unified Docker Compose stack.

## Architecture

### Data Flow
```
Telemetry Agent (mqtt_coordinator.py on Raspberry Pi)
        ↓ MQTT (telemetry)
        ↑ MQTT (cmd/extract_event)
Mosquitto Broker (RSA VPS)
        ↓ telemetry
        ↑ commands
Telegraf (mqtt_consumer + topic_parsing in Docker)
        ↓
InfluxDB 2.7 (time-series DB, 90-day retention)
        ↓
Grafana 11.2.0 (Hub + Detail dashboards & alerts)

Node-RED Dashboard → MQTT (extract_event cmd) → Estaciones
Estaciones         → MQTT (extract_event/res)  → Node-RED Dashboard
```

### MQTT Topic Structure

**Hierarchical namespace:** `org/app/capability/id/category/subcategory`

```
rsa/seismic/smart/<station_id>/telemetry/state              # Connection status
rsa/seismic/smart/<station_id>/telemetry/health             # CPU temp, disk, RAM, uptime
rsa/seismic/smart/<station_id>/telemetry/heartbeat          # Last event timestamp
rsa/seismic/smart/<station_id>/events/detected              # Seismic event notifications
rsa/seismic/smart/<station_id>/events/data                  # Seismic event details
rsa/seismic/smart/<target_id>/cmd/extract_event             # Comando de extracción (→ estaciones)
rsa/seismic/smart/<station_id>/cmd/extract_event/res        # Respuesta de extracción (← estaciones)
```

**Nota:** `<target_id>` puede ser el ID de una estación específica (`DEV00`, `DEV01`, `CHA01`, `CHA02`, `TEN01`) o `broadcast` para enviar a todas las estaciones simultáneamente.

**Topic parsing**: Telegraf extracts `station_id` and `data_type` as indexed tags from the topic hierarchy, enabling per-station filtering in dashboards.

### Telemetry Metrics

**State message** (published on connect/disconnect):
- `status`: "online" or "offline"
- `timestamp`: ISO 8601 timestamp

**Health message** (every 10 seconds):
- `temp_cpu`: CPU temperature (°C)
- `disk_percent`: Disk usage percentage (0-100%)
- `ram_percent`: RAM usage percentage (0-100%)
- `load_avg_15m`: Load average (15 min)
- `uptime_s`: System uptime (seconds) — read from `/proc/uptime`
- `timestamp`: ISO 8601 timestamp

**Heartbeat message** (every 60 seconds):
- `last_event`: Timestamp of last seismic event
- `timestamp`: ISO 8601 timestamp

**Event detected message** (10% probability per cycle):
- `event_id`: Unique event identifier
- `amplitude`: Peak ground acceleration
- `confidence`: Detection confidence score
- `timestamp`: ISO 8601 timestamp

### Alert Conditions
- **Station down**: LWT received or no data for X seconds
- **Prolonged silence**: `last_event_ts` exceeds threshold
- **High temperature**: `temp_cpu` > 60°C
- **High disk usage**: `disk_percent` > 90%
- **High RAM usage**: `ram_percent` > 85%

### Dashboard Architecture (Hub + Detail)

Grafana uses a two-dashboard approach with automatic provisioning:

- **seismic_monitor.json** (Hub): Vista general de todas las estaciones con enlaces de navegación
- **health.json** (Detail): Vista técnica detallada por estación — CPU, RAM, disco, historial (gauges + time series)
- Queries use Flux with InfluxDB Tags and aggregation functions
- Dynamic `${station}` template variable for per-station filtering

## Directory Structure

```
RSA-Intern-TIG-MQTT/
├── .gitignore
├── AGENTS.md                             # This file
├── README.md                             # Project documentation
│
├── services/
│   ├── docker-unified/                   # ✅ Active Docker stack
│   │   ├── docker-compose.yml            # Unified TIG stack (InfluxDB + Telegraf + Grafana)
│   │   ├── telegraf.conf                 # Telegraf config (MQTT consumer + topic_parsing)
│   │   ├── .env.example                  # Environment variables template
│   │   ├── .gitignore                    # Excludes .env
│   │   ├── COMPARISON.md                 # Comparison with individual services approach
│   │   └── README.md                     # Deployment documentation
│   │
│   ├── node-red/                         # ✅ Panel de control remoto
│   │   ├── docker-compose.yml            # Stack Node-RED (puerto 1880, red rsa_network)
│   │   ├── flows.json                    # Flujos exportados y versionados en Git
│   │   ├── package.json                  # Dependencias (node-red-dashboard)
│   │   ├── .env.example                  # Plantilla de variables de entorno
│   │   └── .env                          # Credenciales reales (gitignored)
│   │
│   └── grafana/
│       └── provisioning/                 # Mounted by docker-unified as ../grafana/provisioning
│           ├── dashboards/
│           │   ├── dashboards.yml        # Auto-provisioning config (folder: RSA - Seismic)
│           │   ├── seismic_monitor.json  # Hub dashboard: multi-station overview
│           │   └── health.json           # Detail dashboard: per-station health
│           └── datasources/
│               └── influxdb.yml          # InfluxDB datasource (Flux, env vars)
```

## Development Setup

### Prerequisites
- **Docker & Docker Compose v2**: For running TIG stack
- **MQTT Broker**: Mosquitto or other (can be local or remote)

### Quick Start

**1. Configure credentials**:
```bash
cd services/docker-unified
cp .env.example .env
nano .env
```

**2. Start the stack**:
```bash
docker compose up -d
```

**3. Access services**:
- InfluxDB UI: http://localhost:8086
- Grafana: http://localhost:3000 (admin credentials from `.env`)

### Troubleshooting

**Docker containers fail to start**:
- Check logs: `docker compose logs -f`
- Ensure ports 8086 and 3000 are not in use

**No data in InfluxDB**:
- Verify Telegraf is running: `docker compose logs telegraf`
- Check MQTT topics match agent configuration
- Inspect InfluxDB bucket: http://localhost:8086 → Data Explorer

**Telegraf not parsing station IDs**:
- Verify `topic_parsing` is configured in `telegraf.conf`
- Tags `station_id` and `data_type` should appear in InfluxDB measurements

## Important Notes

### Deployment
The project uses a single unified `docker-compose.yml` in `services/docker-unified/` that orchestrates all three services (InfluxDB, Telegraf, Grafana) with:
- A self-managed `monitoring` bridge network
- Bind mounts to `/home/rsa/data/` for persistent storage
- Health checks on InfluxDB and Grafana
- Environment variable injection for all credentials

### Grafana Provisioning
The `docker-compose.yml` mounts dashboards from a relative path:
```yaml
- ../grafana/provisioning:/etc/grafana/provisioning:ro
```
This means `services/grafana/provisioning/` is the source of truth for dashboards and datasources.

### Configuration Management
- All secrets in `.env` (gitignored for security)
- Use `.env.example` as template
- Telegraf config uses `${MQTT_BROKER}`, `${INFLUXDB_TOKEN}`, etc.
- Docker services inject variables automatically

### MQTT Topic Evolution
- **Original**: `rsa/telemetry/<station_id>/{state,env,disk,frames,meta}`
- **Current**: `rsa/seismic/smart/<station_id>/{telemetry,events}/{state,health,heartbeat,detected,data}`

## Related Projects

This monitoring system consumes telemetry from the **RSA-Acelerografo** project:
- Acelerógrafo stations run on Raspberry Pi devices
- They acquire seismic data, convert to Mini-SEED format, and upload to Google Drive
- The MQTT agent (`mqtt_coordinator.py`) publishes health and event telemetry

## Project Context

**Autor:** Martin Bravo
**Supervisor:** Milton Muñoz
**Institución:** Red Sísmica del Austro (RSA) — Universidad de Cuenca
**Periodo:** Octubre 2025 – Enero 2026
**Last Updated**: May 12, 2026
**Project Status**: En desarrollo activo — Se incorporó panel de control Node-RED para comandos remotos.
