# Dashboard de Monitoreo en Tiempo Real — Red Sísmica del Austro

## Descripción general

Sistema de **monitoreo en tiempo real** para la **Red Sísmica del Austro (RSA)**, diseñado para supervisar el estado operativo de estaciones de acelerógrafos distribuidas. Basado en el stack **TIG (Telegraf, InfluxDB, Grafana)** con **integración MQTT**.

**Estado del Proyecto: 100% completado — ENTREGADO** ✓

---

## Arquitectura

```
Agente de Telemetría (mqtt_coordinator.py on Raspberry Pi)
        ↓ MQTT
Broker Mosquitto (RSA)
        ↓
┌─────────────────┐
│    Telegraf      │  mqtt_consumer → influxdb_v2 output
│  (Container 1)  │  Parsea topics y extrae station_id + data_type
└────────┬────────┘
         ↓
┌─────────────────┐
│    InfluxDB      │  Series temporales · Puerto 8086
│  (Container 2)  │  Retención: 90 días
└────────┬────────┘
         ↓
┌─────────────────┐
│    Grafana       │  Dashboards + alertas · Puerto 3000
│  (Container 3)  │  Provisioning automático
└─────────────────┘
```

### Tópicos MQTT

```
rsa/seismic/smart/<station_id>/telemetry/state      # Estado online/offline
rsa/seismic/smart/<station_id>/telemetry/health     # CPU, disco, RAM, uptime
rsa/seismic/smart/<station_id>/telemetry/heartbeat  # Último evento sísmico
rsa/seismic/smart/<station_id>/events/detected      # Notificación de eventos
rsa/seismic/smart/<station_id>/events/data          # Datos del evento
```

Telegraf extrae `station_id` y `data_type` como tags indexados mediante `topic_parsing`.

### Métricas de salud

| Métrica | Descripción | Fuente |
|---------|-------------|--------|
| `temp_cpu` | Temperatura CPU (°C) | `/sys/class/thermal/` |
| `disk_percent` | Uso de disco (%) | `os.statvfs('/')` |
| `ram_percent` | Uso de RAM (%) | `/proc/meminfo` |
| `load_avg_15m` | Carga promedio 15 min | `os.getloadavg()` |
| `uptime_s` | Tiempo activo (s) | `/proc/uptime` |

### Alertas

| Condición | Umbral |
|-----------|--------|
| Caída de estación | LWT o sin datos > X s |
| Temperatura alta | `temp_cpu` > 60°C |
| Disco alto | `disk_percent` > 90% |
| RAM alta | `ram_percent` > 85% |
| Silencio prolongado | `last_event` excede umbral |

### Dashboards

- **seismic_monitor.json** (Hub): Vista general multi-estación con enlaces de navegación
- **health.json** (Detalle): Métricas por estación — gauges de CPU, RAM, disco + series temporales

---

## Estructura del repositorio

```
RSA-Intern-TIG-MQTT/
├── .gitignore
├── AGENTS.md                             # Guía para agentes de IA
├── README.md                             # Este archivo
│
├── services/
│   ├── docker-unified/                   # Stack Docker activo
│   │   ├── docker-compose.yml            # InfluxDB + Telegraf + Grafana
│   │   ├── telegraf.conf                 # Config con MQTT consumer + topic_parsing
│   │   ├── .env.example                  # Plantilla de variables de entorno
│   │   ├── .gitignore
│   │   └── COMPARISON.md                 # Comparación con enfoque separado
│   │
│   └── grafana/
│       └── provisioning/                 # Montado por docker-unified
│           ├── dashboards/
│           │   ├── dashboards.yml        # Config de provisioning automático
│           │   ├── seismic_monitor.json  # Dashboard Hub
│           │   └── health.json           # Dashboard Detalle
│           └── datasources/
│               └── influxdb.yml          # Datasource InfluxDB (Flux)
```

---

## Instalación y uso

### 1. Configurar credenciales

```bash
cd services/docker-unified
cp .env.example .env
nano .env
```

Variables clave:
```bash
MQTT_BROKER=192.168.1.100       # IP del broker Mosquitto
MQTT_USERNAME=rsa_user
MQTT_PASSWORD=secure_password
INFLUXDB_TOKEN=$(openssl rand -hex 32)
GRAFANA_ADMIN_PASSWORD=secure_password
```

### 2. Iniciar el stack

```bash
docker compose up -d
```

### 3. Verificar estado

```bash
docker compose ps
```

Salida esperada:
```
NAME             STATUS         PORTS
rsa-influxdb     Up (healthy)   0.0.0.0:8086->8086/tcp
rsa-telegraf     Up
rsa-grafana      Up (healthy)   0.0.0.0:3000->3000/tcp
```

### 4. Acceder a las interfaces

| Servicio | URL | Credenciales |
|----------|-----|--------------|
| InfluxDB | http://localhost:8086 | `INFLUXDB_ADMIN_USER` / `INFLUXDB_ADMIN_PASSWORD` |
| Grafana | http://localhost:3000 | `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` |

---

## Operación

### Ver logs

```bash
# Todos los servicios
docker compose logs -f

# Servicio específico
docker compose logs -f telegraf
```

### Reiniciar un servicio

```bash
# Útil después de cambiar telegraf.conf
docker compose restart telegraf
```

### Detener el stack

```bash
# Detener (mantiene datos)
docker compose down

# Detener y eliminar datos (⚠️ CUIDADO)
docker compose down -v
```

### Persistencia de datos

Los datos se almacenan en bind mounts del host:
- **InfluxDB**: `/home/rsa/data/influxdb/data`
- **Grafana**: `/home/rsa/data/grafana`

### Persistir dashboards personalizados

Si creas un dashboard manualmente en Grafana:

1. **Exportar**: Dashboard → Share → Export → Save to file
2. **Copiar** el JSON a `services/grafana/provisioning/dashboards/`
3. **Commitear** para que sea parte del repositorio

---

## Verificación del flujo de datos

### 1. Verificar que Telegraf recibe datos MQTT

```bash
docker compose logs -f telegraf | grep mqtt_consumer
```

### 2. Consultar datos en InfluxDB

Accede a http://localhost:8086 → Data Explorer:
```flux
from(bucket: "telemetry")
  |> range(start: -1h)
  |> filter(fn: (r) => r["_measurement"] == "rsa")
```

### 3. Suscribirse directamente al broker

```bash
mosquitto_sub -h <MQTT_BROKER> -u <USERNAME> -P <PASSWORD> -t "rsa/seismic/smart/#" -v
```

---

## Troubleshooting

| Problema | Solución |
|----------|----------|
| Contenedores no inician | `docker compose logs -f` — verificar puertos 8086/3000 |
| Sin datos en InfluxDB | Verificar que Telegraf recibe MQTT: `docker compose logs telegraf` |
| Telegraf no parsea station_id | Verificar `topic_parsing` en `telegraf.conf` |
| Grafana sin datasource | Verificar `services/grafana/provisioning/datasources/influxdb.yml` |
| Error de red Docker | La red `monitoring` se crea automáticamente con `docker compose up` |

---

## Proyectos relacionados

Este sistema consume telemetría del proyecto **RSA-Acelerografo**:
- Estaciones Raspberry Pi adquieren datos sísmicos
- Convierten a formato Mini-SEED y suben a Google Drive
- El agente MQTT (`mqtt_coordinator.py`) publica métricas de salud y eventos

---

## Autoría

**Autor:** Martin Bravo
**Supervisor:** Milton Muñoz
**Institución:** Red Sísmica del Austro (RSA) — Universidad de Cuenca
**Periodo:** Octubre 2025 – Enero 2026
**Última actualización:** Febrero 23, 2026
