# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Real-time monitoring dashboard for the **Red Sísmica del Austro (RSA)** seismic network. This system uses the **TIG stack (Telegraf, InfluxDB, Grafana)** with **MQTT integration** to collect, store, and visualize telemetry metrics from distributed accelerograph stations.

**Project Status**: ~70% complete. Core components (telemetry agent, Docker services, Telegraf config) are implemented and tested. The system has been validated end-to-end with proof-of-concept dashboards. Remaining work focuses on production hardening, unified deployment, and documentation.

## Architecture

### Data Flow
```
Telemetry Agent (Python on Raspberry Pi)
        ↓ MQTT
Mosquitto Broker (RSA)
        ↓
Telegraf (mqtt_consumer in Docker)
        ↓
InfluxDB (time-series DB, 90-day retention)
        ↓
Grafana (dashboards & alerts)
```

### MQTT Topic Structure (Implemented)

**Hierarchical namespace:** `org/app/capability/id/category/subcategory`

```
rsa/seismic/smart/<station_id>/telemetry/state      # Connection status
rsa/seismic/smart/<station_id>/telemetry/health     # CPU temp, disk, uptime
rsa/seismic/smart/<station_id>/telemetry/heartbeat  # Last event timestamp
rsa/seismic/smart/<station_id>/events/detected      # Seismic event notifications
rsa/seismic/smart/<station_id>/events/data          # Seismic event details
telemetry/<station_id>/data                         # Legacy format (deprecated)
```

**Topic configuration (QoS, retain):** [config/configuracion_mqtt.json](config/configuracion_mqtt.json)

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

## Current State

**Project Status: ~70% Complete** ✓ Core components functional, integration in progress

### ✅ Implemented (Functional)

**Telemetry Agent:**
- [scripts/agent/cliente_mqtt.py](scripts/agent/cliente_mqtt.py): Full telemetry agent (10 KB)
  - MQTT connection with authentication via environment variables
  - Last Will Testament (LWT) for disconnect detection
  - Multi-metric publishing: state, health, heartbeat, events
  - Real system uptime reading (`/proc/uptime`)
  - Simulated metrics: CPU temp (40-60°C), disk space (1-64 GB)
  - Automatic reconnection handling
  - File logging
  - Seismic event simulation (10% probability)

**Docker Infrastructure:**
- [scripts/influxdb/docker-compose.yml](scripts/influxdb/docker-compose.yml): InfluxDB 2.7 service
  - Auto-initialization with admin user/org/bucket
  - Persistent volume (`influxdb_data`)
  - Environment-based configuration
  - Port 8086 exposed
- [scripts/grafana/docker-compose.yml](scripts/grafana/docker-compose.yml): Grafana 11.2.0 service
  - Admin credentials via `.env`
  - Timezone: America/Guayaquil
  - Provisioning folders prepared
  - Port 3000 exposed

**Telegraf Configuration:**
- [scripts/telegraf/telegraf.conf.example](scripts/telegraf/telegraf.conf.example): MQTT consumer configured
  - Input: `mqtt_consumer` for all topic types
  - Output: `influxdb_v2` (partially configured)
  - Environment variable integration

**Configuration:**
- [config/configuracion_mqtt.json](config/configuracion_mqtt.json): MQTT topic structure
  - Hierarchical namespace: `org/app/capability/id`
  - QoS and retain settings per topic type
- [.env.example](.env.example): Environment variable template
  - MQTT credentials
  - InfluxDB admin/org/bucket/retention
  - All secrets externalized

**Documentation:**
- [docs/](docs/): 12 screenshots showing the system working end-to-end
  - Telegraf consuming MQTT messages
  - InfluxDB storing time-series data
  - Grafana dashboards visualizing metrics
  - **Proof of concept validated** ✓

### ⚠️ Partially Implemented

- **Telegraf Docker service**: Configuration exists, but no docker-compose.yml
- **Grafana provisioning**: Folders created, but datasource config missing
- **InfluxDB retention**: Variable defined, needs verification (should be 90 days)

### ❌ Not Yet Implemented

- Unified `docker-compose.yml` at project root (currently split into 2 files)
- Grafana datasource provisioning (`provisioning/datasources/*.yml`)
- Grafana dashboard JSON exports (dashboards exist but not persisted)
- Alert rules in Grafana (station down, high temp, low disk, prolonged silence)
- Multi-station simulator (50-100 stations for load testing)
- `config/configuracion_dispositivo.json.example` template
- Setup script (`setup.sh`) for initialization
- User manuals (installation, operation, troubleshooting)

## Configuration Files

Located in [config/](config/):
- `configuracion_mqtt.json`: MQTT broker connection settings
  - `serverAddress`: Broker IP/hostname
  - `username`, `password`: Authentication
  - `topicStatus`: Status topic (e.g., "status")
- `configuracion_dispositivo.json`: Station device configuration
  - `dispositivo.id`: Station ID (e.g., "NOM00")
  - `dispositivo.modo_adquisicion`: "online" or "offline"

## Development Setup

### Prerequisites
- **Docker & Docker Compose**: For running TIG stack
- **Micromamba** (or conda/mamba): For Python environment
- **MQTT Broker**: Mosquitto or other (can be local or remote)

### Quick Start

**1. Clone and configure**:
```bash
cd /home/rsa/git/rsa/RSA-Intern-TIG-MQTT

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

**3. Create Docker network**:
```bash
docker network create monitoring
```

**4. Start InfluxDB**:
```bash
cd scripts/influxdb
docker-compose up -d
```

**5. Start Grafana**:
```bash
cd ../grafana
docker-compose up -d
```

**6. Run telemetry agent**:
```bash
cd /home/rsa/git/rsa/RSA-Intern-TIG-MQTT
python scripts/agent/cliente_mqtt.py
```

**Access services**:
- InfluxDB UI: http://localhost:8086
- Grafana: http://localhost:3000 (admin credentials from `.env`)

### Troubleshooting

**Agent fails to connect to MQTT broker**:
- Check `MQTT_BROKER`, `MQTT_USERNAME`, `MQTT_PASSWORD` in `.env`
- Test broker connectivity: `telnet <broker> 1883`

**Docker containers fail to start**:
- Verify Docker network exists: `docker network ls | grep monitoring`
- Check logs: `docker-compose logs -f`
- Ensure ports 8086 and 3000 are not in use

**No data in InfluxDB**:
- Verify Telegraf is running (currently needs manual setup)
- Check MQTT topics match agent configuration
- Inspect InfluxDB bucket: http://localhost:8086 → Data Explorer

## Related Projects

This monitoring system consumes telemetry from the **RSA-Acelerografo** project:
- Acelerógrafo stations run on Raspberry Pi devices
- They acquire seismic data, convert to Mini-SEED format, and upload to Google Drive
- The MQTT client in this project is based on the acelerógrafo's status reporting client

## Directory Structure

```
RSA-Intern-TIG-MQTT/
├── .env.example                    # Environment variables template
├── .gitignore                      # Excludes .env, logs, local configs
├── CLAUDE.md                       # This file
├── README.md                       # Project documentation
│
├── config/
│   ├── configuracion_mqtt.json    # MQTT topic structure & QoS settings ✓
│   └── configuracion_dispositivo.json  # (gitignored, needs .example)
│
├── scripts/
│   ├── agent/
│   │   └── cliente_mqtt.py        # Telemetry agent (10 KB, COMPLETE) ✓
│   ├── telegraf/
│   │   ├── telegraf.conf.example  # Telegraf config (549 KB) ✓
│   │   └── influxdb.conf.example  # Basic output config ✓
│   ├── influxdb/
│   │   └── docker-compose.yml     # InfluxDB 2.7 service ✓
│   └── grafana/
│       └── docker-compose.yml     # Grafana 11.2.0 service ✓
│
├── examples/
│   ├── mqtt/
│   │   └── cliente_mqtt.py        # Duplicate of agent (legacy)
│   └── grafana/
│       └── provisioning/
│           └── datasources/       # Empty (needs datasource.yml)
│
├── docs/                           # 12 screenshots of working system ✓
│   ├── Dashboard.png
│   ├── Telegraf, Influx, MQTT y Dashboard.png
│   ├── bucket_configurado.png
│   ├── telegraf_configuracion.png
│   └── ... (8 more)
│
└── env/
    └── mseed_py39.lock             # Micromamba lock file
```

**Key files:**
- ✓ = Implemented and functional
- Blank = Not yet implemented

## Next Steps for Development

### High Priority (Required for Production)

1. **Unify Docker Compose**: Create root `docker-compose.yml` integrating all services
   - Combine InfluxDB, Telegraf, and Grafana
   - Add `depends_on` for correct startup order
   - Use shared `monitoring` network
   - Include Telegraf service (currently missing)

2. **Complete Telegraf Setup**:
   - Create `docker-compose.yml` for Telegraf service
   - Configure `outputs.influxdb_v2` with token, org, bucket
   - Generate InfluxDB admin token and add to `.env`

3. **Grafana Provisioning**:
   - Create `provisioning/datasources/influxdb.yml`
   - Export existing dashboards to JSON files
   - Configure basic alert rules (station down, high temp, low disk)

4. **Create Setup Script** (`setup.sh`):
   - Create Docker network: `docker network create monitoring`
   - Copy `.env.example` to `.env` with prompts
   - Generate InfluxDB token automatically
   - Create required directories

5. **Configuration Templates**:
   - Create `config/configuracion_dispositivo.json.example`
   - Document expected JSON structure
   - Add validation examples

### Medium Priority (Enhancements)

6. **Multi-Station Simulator**:
   - Script to launch N agent instances with dynamic IDs
   - Programmable failure scenarios (disconnect, high temp, low disk)
   - Load testing for 50-100 stations

7. **Documentation**:
   - Installation guide (step-by-step)
   - Operation manual (starting/stopping services, viewing logs)
   - Troubleshooting guide (common errors, debugging)

8. **Code Cleanup**:
   - Remove duplicate `examples/mqtt/cliente_mqtt.py`
   - Consolidate configuration files
   - Add Python requirements.txt or environment.yml

### Low Priority (Optimizations)

9. **Additional Metrics**:
   - RAM usage
   - CPU percentage
   - Network throughput
   - Process count

10. **Automated Testing**:
    - Unit tests for `cliente_mqtt.py`
    - Integration tests for TIG stack
    - CI/CD pipeline (GitHub Actions)

## Important Notes

### System Already Validated ✓
The 12 screenshots in [docs/](docs/) demonstrate that the complete TIG+MQTT integration has been tested successfully:
- Telegraf consuming MQTT messages in real-time
- InfluxDB storing time-series data in the "rsa" bucket
- Grafana visualizing metrics with live dashboards
- All components communicating correctly

**Status**: Proof of concept is functional. Next phase is production hardening.

### Docker Network Requirements
Both docker-compose files use external network `monitoring`:
```yaml
networks:
  monitoring:
    external: true
```

**Before starting services**, create the network:
```bash
docker network create monitoring
```

### MQTT Topic Evolution
The implemented topic structure is more advanced than the original specification:
- **Original**: `rsa/telemetry/<station_id>/{state,env,disk,frames,meta}`
- **Implemented**: `rsa/seismic/smart/<station_id>/{telemetry,events}/{state,health,heartbeat,detected,data}`

**Benefits**:
- Clear namespace hierarchy (org/app/capability)
- Separation of telemetry vs. events
- Scalable for multiple applications beyond seismic monitoring
- Follows MQTT best practices

### Configuration Management
- All secrets moved to `.env` (gitignored for security)
- Use `.env.example` as template
- Agent reads environment variables via `python-dotenv`
- Docker services inject variables automatically

### Running the Telemetry Agent

**Prerequisites**:
```bash
micromamba create -n tig-mqtt python=3.9 -y
micromamba activate tig-mqtt
micromamba install -c conda-forge paho-mqtt python-dotenv -y
```

**Create `.env` file** with real credentials:
```bash
cp .env.example .env
# Edit .env with your MQTT broker details
```

**Run agent**:
```bash
cd /home/rsa/git/rsa/RSA-Intern-TIG-MQTT
python scripts/agent/cliente_mqtt.py
```

**Logs** are written to `log-files/` (auto-created on first run)

## Project Context

**Author:** Martin Bravo
**Supervisor:** Milton Muñoz
**Institution:** Red Sísmica del Austro (RSA) — Universidad de Cuenca
**Period:** October 2025 - Present
**Last Updated**: November 18, 2025
**Project Status**: 70% complete — Core functional, integration in progress
