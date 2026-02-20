# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Project Overview

Real-time monitoring dashboard for the **Red Sísmica del Austro (RSA)** seismic network. This system uses the **TIG stack (Telegraf, InfluxDB, Grafana)** with **MQTT integration** to collect, store, and visualize telemetry metrics from distributed accelerograph stations.

**Project Status**: 100% complete — DELIVERED. Core components (telemetry agent, multi-station simulator, Docker services, Telegraf config, Grafana provisioning) are implemented, tested, and validated. The system has been delivered end-to-end with production-ready dashboards and unified deployment.

## Architecture

### Data Flow
```
Telemetry Agent / Station Simulator (Python)
        ↓ MQTT
Mosquitto Broker (RSA)
        ↓
Telegraf (mqtt_consumer + topic_parsing in Docker)
        ↓
InfluxDB 2.7 (time-series DB, 90-day retention)
        ↓
Grafana 11.2.0 (Hub + Detail dashboards & alerts)
```

### MQTT Topic Structure (Implemented)

**Hierarchical namespace:** `org/app/capability/id/category/subcategory`

```
rsa/seismic/smart/<station_id>/telemetry/state      # Connection status
rsa/seismic/smart/<station_id>/telemetry/health     # CPU temp, disk, uptime
rsa/seismic/smart/<station_id>/telemetry/heartbeat  # Last event timestamp
rsa/seismic/smart/<station_id>/events/detected      # Seismic event notifications
rsa/seismic/smart/<station_id>/events/data          # Seismic event details
```

**Topic configuration (QoS, retain):** [configuracion_mqtt.json](config/configuracion_mqtt.json)

**Topic parsing**: Telegraf extracts `station_id` and `data_type` as indexed tags from the topic hierarchy, enabling per-station filtering in dashboards.

### Telemetry Metrics (Implemented)

**State message** (published on connect/disconnect):
- `status`: "online" or "offline"
- `timestamp`: ISO 8601 timestamp

**Health message** (every 10 seconds):
- `temp_cpu`: CPU temperature (°C) — simulated 40-60°C
- `disk_free_gb`: Free disk space (GB) — simulated 1-64 GB
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
- **Low disk space**: `disk_free_gb` < 1 GB

### Dashboard Architecture (Hub + Detail)

Grafana uses a two-dashboard approach with automatic provisioning:

- **seismic_monitor.json** (Hub): Vista general de todas las estaciones con enlaces de navegación
- **health.json** (Detail): Vista técnica detallada por estación — CPU, RAM, disco, historial
- Queries use Flux with InfluxDB Tags and aggregation functions
- Dynamic `${station}` template variable for per-station filtering

## Current State

**Project Status: 100% Complete — DELIVERED** ✓

**Git Branch**: `rev-milton` (latest reviewed branch)

### ✅ Implemented (Functional)

**Telemetry Agent:**
- [services/agent/cliente_mqtt.py](services/agent/cliente_mqtt.py): Single-station telemetry agent (10 KB)
  - MQTT connection with authentication via environment variables
  - Last Will Testament (LWT) for disconnect detection
  - Multi-metric publishing: state, health, heartbeat, events
  - Real system uptime reading (`/proc/uptime`)
  - Simulated metrics: CPU temp (40-60°C), disk space (1-64 GB)
  - Automatic reconnection handling
  - File logging
  - Seismic event simulation (10% probability)

**Multi-Station Simulator:**
- [services/agent/simulacion_estaciones.py](services/agent/simulacion_estaciones.py): Multi-station simulation agent (9.7 KB)
  - Generates NOM00–NOM09 station configs dynamically
  - Per-station MQTT threads with independent logging
  - Failure simulation profiles: high temperature, low disk, silence, station down
  - Configurable lists: `ESTACIONES_CAIDAS`, `ESTACIONES_SILENCIO`
  - Auto-creates per-station config files in `config/`

**Unified Docker Stack:**
- [docker-compose.yml](docker-compose.yml): Unified stack at project root (909 B)
  - **InfluxDB 2.7**: Auto-initialization, persistent volume (`influxdb_data`), port 8086
  - **Telegraf 1.36**: MQTT consumer with `topic_parsing`, mounts config from external path
  - **Grafana 11.2.0**: Provisioned dashboards & datasources, persistent volume (`grafana-data`), port 3000
  - Bridge network `monitoring` (self-managed, not external)
  - All services read credentials from `.env`

**Grafana Provisioning:**
- [services/grafana/provisioning/dashboards/dashboards.yml](services/grafana/provisioning/dashboards/dashboards.yml): Auto-provisioning config (folder: `RSA - Seismic`)
- [services/grafana/provisioning/dashboards/seismic_monitor.json](services/grafana/provisioning/dashboards/seismic_monitor.json): Hub dashboard — multi-station overview
- [services/grafana/provisioning/dashboards/health.json](services/grafana/provisioning/dashboards/health.json): Detail dashboard — per-station health
- [services/grafana/provisioning/datasources/influxdb.yml](services/grafana/provisioning/datasources/influxdb.yml): InfluxDB datasource auto-provisioning (Flux query language)

**Telegraf Configuration:**
- [services/telegraf/telegraf.conf](services/telegraf/telegraf.conf): Production Telegraf config with MQTT consumer
- [services/telegraf/telegraf.conf.example](services/telegraf/telegraf.conf.example): Reference config
- [services/telegraf/docker-compose.yml](services/telegraf/docker-compose.yml): Standalone Telegraf service (external `monitoring` network)
  - Input: `mqtt_consumer` with `topic_parsing` for `station_id` and `data_type` tags
  - Output: `influxdb_v2` with environment variable integration

**Per-Station Configuration (10 stations):**
- [config/configuracion_mqtt.json](config/configuracion_mqtt.json): Base MQTT topic structure (QoS, retain settings)
- `config/configuracion_mqtt_NOM00.json` ... `config/configuracion_mqtt_NOM09.json`: Per-station MQTT configs
- `config/configuracion_dispositivo_NOM00.json` ... `config/configuracion_dispositivo_NOM09.json`: Per-station device configs

**Legacy/Individual Service Configs:**
- [services/influxdb/docker-compose.yml](services/influxdb/docker-compose.yml): Standalone InfluxDB service
- [services/grafana/docker-compose.yml](services/grafana/docker-compose.yml): Standalone Grafana service

**Alternative Unified Deployment:**
- [services/docker-unified/](services/docker-unified/): Complete alternative deployment with its own `docker-compose.yml`, `start.sh`, `.env.example`, `COMPARISON.md`, and `README.md`

**Documentation & Evidence:**
- [docs/](docs/): 27 screenshots + 2 dashboard JSON exports demonstrating end-to-end operation
- [README.md](README.md): Project documentation with architecture and deployment guide

## Configuration Files

Located in [config/](config/):
- `configuracion_mqtt.json`: MQTT broker connection settings
  - `serverAddress`: Broker IP/hostname
  - `username`, `password`: Authentication
  - `topicStatus`: Status topic
- `configuracion_dispositivo_NOMxx.json`: Per-station device configuration
  - `dispositivo.id`: Station ID (e.g., "NOM00")
  - `dispositivo.modo_adquisicion`: "online" or "offline"

## Development Setup

### Prerequisites
- **Docker & Docker Compose v2**: For running TIG stack
- **Micromamba** (or conda/mamba): For Python environment
- **MQTT Broker**: Mosquitto or other (can be local or remote)

### Quick Start

**1. Clone and configure**:
```bash
cd /path/to/RSA-Intern-TIG-MQTT

# Copy environment template
cp .env.example .env

# Edit .env with your credentials
nano .env
```

**2. Set up Python environment**:
```bash
micromamba create -n tig-mqtt python=3.9 -y
micromamba activate tig-mqtt
micromamba install -c conda-forge paho-mqtt python-dotenv -y
```

**3. Start the unified stack**:
```bash
docker compose up -d
```

The unified `docker-compose.yml` creates the `monitoring` bridge network automatically (no need for `docker network create`).

**4. Run telemetry agent** (single station):
```bash
python services/agent/cliente_mqtt.py
```

**5. Run multi-station simulator** (10 stations):
```bash
python services/agent/simulacion_estaciones.py
```

**Access services**:
- InfluxDB UI: http://localhost:8086
- Grafana: http://localhost:3000 (admin credentials from `.env`)

### Troubleshooting

**Agent fails to connect to MQTT broker**:
- Check `MQTT_BROKER`, `MQTT_USERNAME`, `MQTT_PASSWORD` in `.env`
- Test broker connectivity: `telnet <broker> 1883`

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

## Related Projects

This monitoring system consumes telemetry from the **RSA-Acelerografo** project:
- Acelerógrafo stations run on Raspberry Pi devices
- They acquire seismic data, convert to Mini-SEED format, and upload to Google Drive
- The MQTT client in this project is based on the acelerógrafo's status reporting client

## Directory Structure

```
RSA-Intern-TIG-MQTT/
├── .env.example                          # Environment variables template
├── .gitignore                            # Excludes .env, logs, local configs
├── AGENTS.md                             # This file
├── README.md                             # Project documentation
├── docker-compose.yml                    # Unified TIG stack (production)
│
├── config/
│   ├── configuracion_mqtt.json           # Base MQTT topic structure ✓
│   ├── configuracion_mqtt_NOM00..09.json # Per-station MQTT configs (×10) ✓
│   └── configuracion_dispositivo_NOM00..09.json  # Per-station device configs (×10) ✓
│
├── services/
│   ├── agent/
│   │   ├── cliente_mqtt.py               # Single-station telemetry agent ✓
│   │   └── simulacion_estaciones.py      # Multi-station simulator ✓
│   ├── telegraf/
│   │   ├── docker-compose.yml            # Standalone Telegraf service
│   │   ├── telegraf.conf                 # Production config (topic_parsing) ✓
│   │   └── telegraf.conf.example         # Reference config ✓
│   ├── influxdb/
│   │   ├── docker-compose.yml            # Standalone InfluxDB service ✓
│   │   └── influxdb.conf.example         # InfluxDB reference config
│   ├── grafana/
│   │   ├── docker-compose.yml            # Standalone Grafana service ✓
│   │   └── provisioning/
│   │       ├── dashboards/
│   │       │   ├── dashboards.yml        # Provisioning config ✓
│   │       │   ├── seismic_monitor.json  # Hub: multi-station overview ✓
│   │       │   └── health.json           # Detail: per-station health ✓
│   │       └── datasources/
│   │           └── influxdb.yml          # InfluxDB datasource provisioning ✓
│   └── docker-unified/                   # Alternative unified deployment
│       ├── docker-compose.yml
│       ├── start.sh
│       ├── .env.example
│       ├── COMPARISON.md
│       └── README.md
│
├── examples/
│   ├── mqtt/                             # MQTT examples (empty)
│   └── mseed/
│       ├── extract_segment.py            # MiniSEED segment extraction utility
│       └── data/                         # Sample data
│
├── docs/                                 # 27 screenshots + 2 dashboard JSONs
│
└── env/
    └── mseed_py39.lock                   # Micromamba lock file
```

**Key:** ✓ = Implemented and functional

## Important Notes

### Unified vs Individual Docker Compose
The project contains **two deployment approaches**:
1. **Unified** (recommended): Root `docker-compose.yml` — runs all services together with a self-managed bridge network
2. **Individual**: Separate `docker-compose.yml` in `services/influxdb/`, `services/grafana/`, `services/telegraf/` — require an external `monitoring` network (`docker network create monitoring`)

### Telegraf External Mount
The unified `docker-compose.yml` mounts Telegraf config from `../../telegraf-1.36.3/etc/telegraf` (outside the repo). Ensure the Telegraf binary distribution is extracted at the expected sibling path.

### System Validated ✓
Screenshots in [docs/](docs/) demonstrate the complete TIG+MQTT integration:
- Telegraf consuming MQTT messages with topic parsing
- InfluxDB storing time-series data with station tags
- Grafana Hub + Detail dashboards with per-station filtering
- Alert conditions (temperature, disk, silence, station down)

### MQTT Topic Evolution
- **Original**: `rsa/telemetry/<station_id>/{state,env,disk,frames,meta}`
- **Implemented**: `rsa/seismic/smart/<station_id>/{telemetry,events}/{state,health,heartbeat,detected,data}`

### Configuration Management
- All secrets in `.env` (gitignored for security)
- Use `.env.example` as template
- Agent reads environment variables via `python-dotenv`
- Docker services inject variables automatically

## Project Context

**Autor:** Martin Bravo
**Supervisor:** Milton Muñoz
**Institución:** Red Sísmica del Austro (RSA) — Universidad de Cuenca
**Periodo:** Octubre 2025 – Enero 2026
**Last Updated**: February 19, 2026
**Project Status**: 100% complete — DELIVERED
