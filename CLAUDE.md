# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Real-time monitoring dashboard for the **Red Sísmica del Austro (RSA)** seismic network. This system uses the **TIG stack (Telegraf, InfluxDB, Grafana)** with **MQTT integration** to collect, store, and visualize telemetry metrics from distributed accelerograph stations.

The project is in **early development** phase - directory structure exists but most implementation components (Docker setup, Telegraf configs, Grafana dashboards, telemetry agents) are not yet implemented.

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

### MQTT Topic Structure
```
rsa/telemetry/<station_id>/state    # online/offline status
rsa/telemetry/<station_id>/env      # CPU temperature
rsa/telemetry/<station_id>/disk     # disk space
rsa/telemetry/<station_id>/frames   # uptime
rsa/telemetry/<station_id>/meta     # last event timestamp
```

### Telemetry Metrics
- `online`: Connection status (True/False)
- `temp_cpu`: CPU temperature (°C)
- `disk_free_gb`: Free disk space (GB)
- `uptime_s`: Uptime since last boot (seconds)
- `last_event_ts`: Timestamp of last seismic event

### Alert Conditions
- **Station down**: LWT received or no data for X seconds
- **Prolonged silence**: `last_event_ts` exceeds threshold
- **High temperature**: `temp_cpu` > 60°C
- **Low disk space**: `disk_free_gb` < 1 GB

## Current State

**Implemented:**
- [examples/mqtt/cliente_mqtt.py](examples/mqtt/cliente_mqtt.py): MQTT client example (copied from RSA-Acelerografo project)
- Configuration files in [config/](config/)

**Not yet implemented:**
- Docker Compose setup for TIG stack
- Telegraf configuration (mqtt_consumer)
- InfluxDB setup and retention policies
- Grafana dashboards and alert rules
- Python telemetry agent simulator
- Multi-station simulation scripts

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

### Python Dependencies
```bash
# Create virtual environment with micromamba
micromamba create -n tig-mqtt python=3.9 -y
micromamba activate tig-mqtt

# Install MQTT client library
micromamba install -c conda-forge paho-mqtt -y
```

### Running the MQTT Client Example
```bash
python examples/mqtt/cliente_mqtt.py
```

**Note:** The example uses hardcoded paths from the acelerografo project:
- `/home/rsa/projects/acelerografo/configuracion/`
- `/home/rsa/projects/acelerografo/log-files/`

These paths need to be updated for this project.

## Related Projects

This monitoring system consumes telemetry from the **RSA-Acelerografo** project:
- Acelerógrafo stations run on Raspberry Pi devices
- They acquire seismic data, convert to Mini-SEED format, and upload to Google Drive
- The MQTT client in this project is based on the acelerógrafo's status reporting client

## Directory Structure

```
RSA-Intern-TIG-MQTT/
├── config/                 # MQTT and device configuration files
├── scripts/
│   ├── agent/             # (TODO) Telemetry agent simulator
│   ├── telegraf/          # (TODO) Telegraf configuration
│   ├── influxdb/          # (TODO) InfluxDB setup
│   └── grafana/           # (TODO) Dashboards and alerts
├── examples/
│   └── mqtt/              # MQTT client example
├── docs/                  # (empty) Documentation
└── env/                   # (empty) Environment files
```

## Next Steps for Development

1. Create `docker-compose.yml` with Telegraf, InfluxDB, and Grafana services
2. Configure Telegraf as MQTT consumer for RSA topic structure
3. Set up InfluxDB with 90-day retention policy
4. Develop Python telemetry agent that publishes realistic metrics
5. Create Grafana dashboards (network overview + per-station detail)
6. Implement alert rules in Grafana
7. Build multi-station simulator (50-100 stations) for load testing

## Project Context

**Author:** Martin Bravo
**Supervisor:** Milton Muñoz
**Institution:** Red Sísmica del Austro (RSA) — Universidad de Cuenca
**Period:** October 2025
