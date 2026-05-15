# Dashboard de Monitoreo en Tiempo Real — Red Sísmica del Austro

## Descripción general

Sistema de **monitoreo en tiempo real** para la **Red Sísmica del Austro (RSA)**, diseñado para supervisar el estado operativo de estaciones de acelerógrafos distribuidas. Basado en el stack **TIG (Telegraf, InfluxDB, Grafana)** con **integración MQTT**.

**Estado del Proyecto: En desarrollo activo** — Stack TIG entregado ✓ · Panel de control Node-RED incorporado ✓

---

## Arquitectura

```
Estaciones Raspberry Pi (mqtt_coordinator.py)
        ↓ telemetría MQTT        ↑ comandos MQTT
Broker Mosquitto (VPS externo)
   ↓ telemetría                      ↑ cmd/res
┌─────────────────┐         ┌──────────────────────┐
│    Telegraf      │         │      Node-RED         │
│  (Container 1)  │         │    (Container 4)      │
│  MQTT Consumer  │         │  Dashboard · Puerto   │
└────────┬────────┘         │  1880 · Panel de      │
         ↓                  │  control remoto       │
┌─────────────────┐         └──────────────────────┘
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
# Telemetría (Raspberry Pi → Broker → Telegraf)
rsa/seismic/smart/<station_id>/telemetry/state              # Estado online/offline
rsa/seismic/smart/<station_id>/telemetry/health             # CPU, disco, RAM, uptime
rsa/seismic/smart/<station_id>/telemetry/heartbeat          # Último evento sísmico
rsa/seismic/smart/<station_id>/events/detected              # Notificación de eventos
rsa/seismic/smart/<station_id>/events/data                  # Datos del evento

# Comandos remotos (Node-RED → Broker → Raspberry Pi)
rsa/seismic/smart/<target_id>/cmd/extract_event             # Comando de extracción
rsa/seismic/smart/<station_id>/cmd/extract_event/res        # Respuesta de la estación
```

**Notas:**
- Telegraf extrae `station_id` y `data_type` como tags indexados mediante `topic_parsing`.
- `<target_id>` puede ser un ID de estación específico (`DEV00`, `DEV01`, `CHA01`, `CHA02`, `TEN01`) o `broadcast` para enviar a todas las estaciones.

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
│   ├── docker-unified/                   # Stack Docker activo (TIG)
│   │   ├── docker-compose.yml            # InfluxDB + Telegraf + Grafana
│   │   ├── telegraf.conf                 # Config con MQTT consumer + topic_parsing
│   │   ├── .env.example                  # Plantilla de variables de entorno
│   │   ├── .gitignore
│   │   └── COMPARISON.md                 # Comparación con enfoque separado
│   │
│   ├── node-red/                         # Panel de control remoto
│   │   ├── docker-compose.yml            # Stack Node-RED (puerto 1880)
│   │   ├── flows.json                    # Flujos exportados y versionados
│   │   ├── package.json                  # Dependencias base
│   │   └── settings.js                   # Logging y seguridad de la UI
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
| Node-RED | http://localhost:1880 | *(sin autenticación por defecto)* |
| Node-RED UI | http://localhost:1880/ui | Dashboard del panel de control |

---

## Despliegue — Panel de Control Node-RED

El servicio Node-RED se despliega de forma **independiente** del stack TIG, desde su propio directorio. Se gestiona íntegramente mediante un único volumen persistente de datos para evitar bloqueos del sistema de archivos (`EBUSY`).

### 1. Preparar el entorno y permisos

```bash
sudo mkdir -p /home/rsa/data/nodered
sudo chown -R 1000:1000 /home/rsa/data/nodered

# Copiar configuración base al volumen para el primer arranque
cd services/node-red
cp settings.js package.json /home/rsa/data/nodered/
```

### 2. Iniciar el contenedor

```bash
docker compose up -d

# El primer arranque descargará dependencias de UI si package.json está presente
docker logs -f rsa-nodered
```

### 3. Acceder al panel y configurar credenciales

- **Editor de flujos:** `http://<IP_SERVIDOR>:1880`
- **Dashboard UI:** `http://<IP_SERVIDOR>:1880/ui`

> ⚠️ **Nota de Seguridad:** Las credenciales del broker MQTT se deben ingresar **directamente en la interfaz web** de Node-RED (en la pestaña *Security* del nodo MQTT). El sistema las encriptará y guardará nativamente en el volumen.

### 4. Verificar logs del servicio

```bash
# Logs persistentes propios de Node-RED (configurados en settings.js)
tail -f /home/rsa/data/nodered/nodered.log
```

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

### Stack TIG

| Problema | Solución |
|----------|----------|
| Contenedores no inician | `docker compose logs -f` — verificar puertos 8086/3000 |
| Sin datos en InfluxDB | `docker compose logs telegraf` — verificar conexión MQTT |
| Telegraf no parsea station_id | Verificar `topic_parsing` en `telegraf.conf` |
| Grafana sin datasource | Verificar `services/grafana/provisioning/datasources/influxdb.yml` |
| Error de red Docker | La red `rsa_network` debe crearse antes: `docker network create rsa_network` |

### Node-RED

| Problema | Causa | Solución |
|----------|-------|----------|
| Contenedor en `Restarting` loop | Permisos del volumen `/data` | `sudo chown -R 1000:1000 /home/rsa/data/nodered` |
| Error `EBUSY` al guardar | Montajes de archivos individuales (`:ro`) en Docker | Solo montar el directorio raíz `- /home/rsa/data/nodered:/data` |
| Nodo MQTT en "conectando" | Credenciales incorrectas | Configurar credenciales en la pestaña *Security* del nodo MQTT web |
| Flujos detenidos (faltan tipos) | Módulo UI no instalado | Instalar `node-red-dashboard` desde *Manage Palette* en la web. |

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
**Última actualización:** Mayo 13, 2026
