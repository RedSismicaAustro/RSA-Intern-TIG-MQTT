# Dashboard de Monitoreo y Análisis Sísmico en Tiempo Real — Red Sísmica del Austro

## 📖 Descripción General

Sistema integral de **monitoreo, detección regional, análisis visual y persistencia de eventos sísmicos** para la **Red Sísmica del Austro (RSA)**, diseñado para supervisar en tiempo real la red de estaciones acelerográficas distribuidas.

El sistema combina el stack **TIG (Telegraf, InfluxDB v2, Grafana)**, un servicio de **Correlación Regional Multiestación**, una aplicación interactiva web **Event Analyzer (Streamlit + ObsPy + Plotly)**, un panel de control **Node-RED** y un protocolo automatizado de **Respaldo y Recuperación en la nube (Google Drive)** con soporte para **arquitectura multi-servidor tolerante a fallos**.

---

## 🏛️ Arquitectura del Sistema

```
                      Estaciones Raspberry Pi (mqtt_coordinator.py)
                           ↓ telemetría / detecciones    ↑ comandos
                      Broker Mosquitto Central (VPS Externo)
                           │                               │
       ┌───────────────────┼───────────────────────────────┼──────────────────┐
       │ (telemetría QoS 1)│ (detecciones QoS 1)           │ (metadata QoS 1) │ (cmd QoS 1)
       ▼                   ▼                               ▼                  ▲
┌──────────────┐   ┌──────────────────────────────┐   ┌─────────────────┐     │
│   Telegraf   │   │  rsa-correlator (Primary)    │   │  Event Analyzer │     │
│ (Consumer)   │   │  - Buffer temporal 10s       │   │  - Streamlit UI │     │
└──────┬───────┘   │  - Cooldown 60s              │   │  - ObsPy + DSP  │─────┘
       │           │  - Sesión persistente MQTT   │   │  - Lazy Loading │ (clasificación)
       ▼           └──────────────┬───────────────┘   └────────┬────────┘
┌──────────────┐                  │ (broadcast cmd)            │
│   InfluxDB   │ ◄────────────────┼────────────────────────────┘ (lectura catálogo)
│ (rsa_events) │                  ▼
└──────┬───────┘         Estaciones Sísmicas
       │                 (Extracción MiniSEED → Google Drive)
       ▼                                  │
┌──────────────┐                          ▼
│   Grafana    │                 Google Drive (gdrive:)
│ (Dashboards) │                 ├── /data/events/*.mseed
└──────────────┘                 └── DIA/Datos Estaciones/RSA-Backups/influxdb/ (Backups diarios)
```

---

## 🌐 Arquitectura Multi-Servidor (Roles)

El sistema soporta despliegues en múltiples servidores para redundancia geográfica y tolerancia ante cortes prolongados de energía:

| Característica | Servidor Primario (`rsa-server`) | Servidor Espejo (`home-server`) |
|---|---|---|
| **Rol en `.env`** | `RSA_SERVER_ROLE=primary` | `RSA_SERVER_ROLE=mirror` |
| **Correlador Regional** | **Activo** (`docker compose --profile primary up -d`) | **Inactivo** (no corre contenedor) |
| **Sesión MQTT Correlador** | Persistente (`clean_session=False`) con `client_id` fijo | N/A |
| **Ingesta de Telemetría** | Telegraf permanente en InfluxDB local | Telegraf permanente en InfluxDB local |
| **Visualizador Event Analyzer** | Activo (:8501) | Activo (:8501) |
| **Clasificación Manual** | Publica al broker $\rightarrow$ sincroniza vía Telegraf | Publica al broker $\rightarrow$ sincroniza vía Telegraf |
| **Automatización de Backups** | Systemd Timer activo (02:00 UTC) $\rightarrow$ sube a Drive | Bajo demanda (`restore_events.sh --latest`) |

---

## 📂 Estructura del Repositorio

```text
RSA-Intern-TIG-MQTT/
├── AGENTS.md                             # Guía de contexto y reglas para agentes de IA
├── README.md                             # Este archivo de documentación
│
├── docs/                                 # Documentación técnica, ADRs y blueprints
│   ├── adr/                              # Architecture Decision Records (ej. ADR-016)
│   ├── blueprints/                       # Planes maestros de implementación por fases
│   ├── context/                          # Contextos técnicos de cada componente
│   └── progress/                         # Bitácoras de avance y diagnósticos técnicos
│
├── scripts/
│   ├── correlator/                       # Daemon de Correlación Regional Multiestación
│   │   ├── config.json                   # Umbrales (10s coincidencia, ≥2 estaciones, 60s cooldown)
│   │   ├── Dockerfile                    # Contenedor Python 3.11
│   │   ├── regional_event_correlator.py  # Lógica de buffer deslizante y disparo broadcast
│   │   └── requirements.txt              # paho-mqtt, python-dotenv
│   │
│   └── db_sync/                          # Utilidades de Respaldo y Sincronización
│       ├── backup_events.sh              # Snapshot binario InfluxDB + CSV + Drive + rotación 7d
│       ├── restore_events.sh             # Descarga desde Drive y restauración destructiva
│       ├── mqtt_notify.py                # Publicador de telemetría de backup vía MQTT (QoS 1)
│       ├── Dockerfile                    # Contenedor ligero rsa-db-sync
│       └── requirements.txt              # Dependencias del contenedor utilitario
│
└── services/
    ├── docker-unified/                   # Orquestación Docker Compose unificada
    │   ├── docker-compose.yml            # InfluxDB + Telegraf + Grafana + Correlator + Event Analyzer + DB Sync
    │   ├── telegraf.conf                 # Configuración de métricas y metadatos MQTT
    │   └── .env.example                  # Plantilla maestra de variables de entorno
    │
    ├── event-analyzer/                   # Aplicación Web Streamlit de análisis sísmico
    │   ├── app.py                        # UI principal Streamlit
    │   ├── Dockerfile                    # Contenedor Streamlit + ObsPy + Dash Resampler
    │   ├── requirements.txt              # Dependencias científicas (obspy, plotly, streamlit, etc.)
    │   └── src/                          # Módulos de DSP, filtrado, lectura y cliente InfluxDB
    │
    ├── node-red/                         # Panel de control remoto complementario
    │   ├── docker-compose.yml            # Stack independiente Node-RED (puerto 1880)
    │   ├── flows.json                    # Flujos y lógica de control
    │   ├── package.json                  # Dependencias dashboard
    │   └── settings.js                   # Configuración del motor
    │
    └── systemd/                          # Automatización de tareas programadas en el host
        ├── manage_backup_timer.sh        # Gestor de instalación/desinstalación portable
        ├── rsa-backup-events.service.template # Plantilla del servicio oneshot
        └── rsa-backup-events.timer.template   # Plantilla del temporizador diario (02:00 UTC)
```

---

## 🚀 Guía de Despliegue en Cualquier Servidor

Sigue estos pasos para desplegar el sistema desde cero en cualquier máquina Linux (Ubuntu / Debian / Raspberry Pi OS):

### 1. Requisitos Previos

- **Docker Engine** y **Docker Compose v2** instalados:
  ```bash
  docker --version && docker compose version
  ```
- Usuario actual agregado al grupo `docker`:
  ```bash
  sudo usermod -aG docker $USER
  # (Requiere cerrar sesión y volver a entrar si recién se agregó)
  ```
- **rclone** configurado con un remote a Google Drive (necesario para backups y lectura de trazas MiniSEED):
  ```bash
  rclone listremotes   # Debe mostrar 'gdrive:'
  ```

---

### 2. Clonar el Repositorio y Crear la Red Docker

```bash
cd ~/git/rsa   # o el directorio de tu preferencia
git clone <URL_DEL_REPOSITORIO> RSA-Intern-TIG-MQTT
cd RSA-Intern-TIG-MQTT

# Crear la red compartida rsa_network (requerida por el stack)
docker network create rsa_network || true
```

---

### 3. Configurar Variables de Entorno (`.env`)

```bash
cd services/docker-unified
cp .env.example .env
nano .env
```

Configura las variables según el entorno:

```ini
# ==============================================================================
# Rutas en el Host
# ==============================================================================
DATA_DIR=/home/rsa/data                       # Directorio local para datos persistentes
DRIVE_DIR=/home/rsa/datos_estaciones_drive    # Directorio montado con rclone para trazas MiniSEED

# ==============================================================================
# Credenciales Broker MQTT
# ==============================================================================
MQTT_BROKER=174.138.41.251                    # IP o hostname del broker Mosquitto
MQTT_PORT=1883
MQTT_USERNAME=tu_usuario
MQTT_PASSWORD=tu_contraseña

# ==============================================================================
# Configuración InfluxDB v2
# ==============================================================================
INFLUXDB_ADMIN_USER=admin
INFLUXDB_ADMIN_PASSWORD=contraseña_segura_admin
INFLUXDB_ORG=rsa
INFLUXDB_BUCKET=telemetry
INFLUXDB_EVENTS_BUCKET=rsa_events
INFLUXDB_RETENTION=90d
INFLUXDB_TOKEN=genera_un_token_seguro_con_openssl_rand_hex_32

# ==============================================================================
# Identificador de Telegraf y Grafana
# ==============================================================================
TELEGRAF_CLIENT_ID=events-oficina             # ej. events-oficina o events-home
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=contraseña_grafana

# ==============================================================================
# Rol Multi-Servidor
# ==============================================================================
# Para el servidor principal (oficina):
RSA_SERVER_ROLE=primary
RSA_CORRELATOR_CLIENT_ID=rsa-correlator-primary

# Para el servidor espejo (casa / contingencia):
# RSA_SERVER_ROLE=mirror
# (No definir o comentar RSA_CORRELATOR_CLIENT_ID)

RCLONE_REMOTE="gdrive:DIA/Datos Estaciones/RSA-Backups/influxdb"
```

---

### 4. Iniciar los Contenedores

#### A. En el Servidor Primario (`rsa-server` con Correlador Activo):

```bash
cd services/docker-unified

# Inicia InfluxDB, Telegraf, Grafana, Event Analyzer y el Correlador Regional
docker compose --profile primary up -d --build
```

#### B. En el Servidor Espejo (`home-server` sin Correlador):

```bash
cd services/docker-unified

# Inicia InfluxDB, Telegraf, Grafana y Event Analyzer (sin correlador)
docker compose up -d --build
```

---

### 5. Configurar la Automatización de Respaldos (Systemd)

Para habilitar el respaldo diario automático a las 02:00 UTC con rotación de 7 días:

```bash
cd services/systemd

# 1. Otorgar permisos de ejecución al gestor
chmod +x manage_backup_timer.sh

# 2. Instalar y habilitar el temporizador del sistema
sudo ./manage_backup_timer.sh --install

# 3. Comprobar estado y próxima ejecución
./manage_backup_timer.sh --status

# 4. (Opcional) Probar ejecución manual inmediata vía systemd
sudo ./manage_backup_timer.sh --run-now
```

---

## 🖥️ Servicios y Accesos Web

| Servicio | Puerto Host | URL Local | Descripción |
|---|---|---|---|
| **Event Analyzer** | `8501` / `8050` | http://localhost:8501 | Visualizador interactivo de eventos, filtrado DSP y clasificación |
| **Grafana** | `3000` | http://localhost:3000 | Dashboards de salud de estaciones y telemetría histórica |
| **InfluxDB UI** | `8086` | http://localhost:8086 | Explorador Data Explorer (buckets `telemetry` y `rsa_events`) |
| **Node-RED** | `1880` | http://localhost:1880/ui | Panel de control remoto y disparo manual de eventos |

---

## 💾 Protocolo de Respaldo y Recuperación (Fase 5A)

### Respaldo Manual
```bash
cd scripts/db_sync
bash backup_events.sh
```
- Genera un snapshot binario nativo (`rsa_events_YYYY-MM-DD.tar.gz`).
- Exporta un archivo tabular plano (`rsa_events_YYYY-MM-DD.csv`) con todos los eventos catalogados.
- Sube ambos archivos a `gdrive:DIA/Datos Estaciones/RSA-Backups/influxdb/`.
- Purga respaldos locales y remotos con más de 7 días de antigüedad.
- Emite telemetría JSON con QoS 1 al tópico `rsa/seismic/smart/system/backup`.

### Restauración de Catálogo
```bash
cd scripts/db_sync

# Restaurar la copia más reciente de Google Drive:
bash restore_events.sh --latest

# Restaurar una fecha específica:
bash restore_events.sh --date 2026-08-27
```
> ⚠️ **Advertencia:** La restauración elimina el bucket `rsa_events` actual y lo recrea desde el snapshot. El script solicita confirmación interactiva mostrando el conteo previo de eventos antes de proceder.

---

## 🛠️ Comandos de Operación y Mantenimiento

### Docker Compose
```bash
cd services/docker-unified

# Ver estado de contenedores
docker compose --profile primary ps

# Ver logs en tiempo real
docker compose --profile primary logs -f correlator
docker compose --profile primary logs -f event-analyzer
docker compose --profile primary logs -f telegraf

# Reiniciar un servicio
docker compose --profile primary restart event-analyzer

# Detener el stack manteniendo datos
docker compose --profile primary down
```

### Gestor Systemd
```bash
cd services/systemd

# Ver estado y próxima ejecución del timer
./manage_backup_timer.sh --status

# Seguir logs de ejecuciones de respaldo en journald
./manage_backup_timer.sh --logs -f

# Desinstalar completamente la automatización
sudo ./manage_backup_timer.sh --uninstall
```

---

## 👥 Autoría y Créditos

- **Desarrollo y Arquitectura**: Martin Bravo & Equipo Técnico RSA
- **Supervisión y Dirección**: Milton Muñoz
- **Institución**: Red Sísmica del Austro (RSA) — Universidad de Cuenca
- **Fecha de Actualización**: Agosto 2026 (Fase 5 Completada)
