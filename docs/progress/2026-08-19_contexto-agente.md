# Resumen de Sesión: Integración de InfluxDB con Event Analyzer, Node-RED y Ciclo Cerrado de Clasificación MQTT (Fase 4)

**Fecha**: 2026-08-19  
**Repositorio**: `RSA-Intern-TIG-MQTT`  
**Agente de IA**: Antigravity  
**Usuario**: Milton  

---

## 🎯 Objetivo de la Sesión

Culminar la **Fase 4** del plan de integración de eventos sísmicos en el stack TIG-MQTT: conectar la interfaz web de `Event Analyzer` con `InfluxDB` como fuente única de verdad para el índice de eventos, habilitar la clasificación interactiva (Confirmado/Descartado) vía MQTT con QoS 1, integrar la emisión de metadatos de extracciones manuales desde `Node-RED`, y optimizar la resolución de trazas MiniSEED mediante *Lazy Loading* y normalización de estaciones.

---

## 📂 Estructura del Repositorio Modificada

```text
RSA-Intern-TIG-MQTT/
├── docs/
│   ├── blueprints/
│   │   └── 2026-08-13_influx_sync_implementation_plan.md
│   ├── context/
│   │   ├── docker-compose-nodered_context.md          # [ACTUALIZADO] Emisión dual extract_event + metadata
│   │   ├── docker-compose-tig-mqtt_context.md         # [ACTUALIZADO] Stack 5 servicios y segmentación Telegraf
│   │   ├── event_analyzer_context.md                  # [ACTUALIZADO] Arquitectura InfluxDB + Lazy Loading + Clasificación
│   │   ├── influx_client_context.md                   # [NUEVO] Módulo cliente Flux y publicador QoS 1
│   │   └── regional_event_correlator_context.md       # [ACTUALIZADO] Tópico events_metadata y UUID client ID
│   └── progress/
│       └── 2026-08-19_contexto-agente.md              # [NUEVO] Este documento de transición
├── scripts/
│   └── correlator/
│       ├── config.json                                # Configuración de tópicos (events_metadata)
│       └── regional_event_correlator.py               # Client ID único y emisión de metadatos QoS 1
└── services/
    ├── docker-unified/
    │   ├── .env.example                               # Variables INFLUXDB_EVENTS_BUCKET, TELEGRAF_CLIENT_ID
    │   ├── docker-compose.yml                         # Variables InfluxDB/MQTT para event-analyzer
    │   └── telegraf.conf                              # timestamp_path = "timestamp_utc", namepass/namedrop
    ├── event-analyzer/
    │   ├── requirements.txt                           # influxdb-client>=1.36.0, paho-mqtt>=1.6.1
    │   ├── app.py                                     # Catálogo InfluxDB, format_func, botones confirmar/descartar
    │   └── src/
    │       └── core/
    │           ├── influx_client.py                   # [NUEVO] Clase InfluxEventsClient (Flux query + MQTT publish)
    │           └── reader.py                          # scan_event() dirigido y _normalize_station_variants()
    └── node-red/
        └── flows.json                                 # Build Command dual (cmd/extract_event + events/metadata)
```

---

## ⚙️ Configuración del Entorno y Servicios

1. **InfluxDB v2 (`rsa-influxdb`)**:
   - Bucket `rsa_events` activo con retención infinita (`-r 0`).
   - Medición `seismic_event` para almacenar los 4 tipos de eventos sísmicos.
2. **Telegraf (`rsa-telegraf`)**:
   - Configurado con `timestamp_path = "timestamp_utc"` y `timestamp_format = "2006-01-02T15:04:05.000Z07:00"` en el parser `json_v2`.
   - Garantiza que las actualizaciones de clasificación (Tipo 3 y 4) no sobrescriban el timestamp `_time` con la hora del clic.
   - Segmentación de outputs: `namedrop = ["seismic_event"]` para el bucket `telemetry` y `namepass = ["seismic_event"]` para `rsa_events`.
3. **Node-RED (`rsa-nodered`)**:
   - Actualizado en volumen `/data/flows.json` para publicar en paralelo a `cmd/extract_event` y `events/metadata`.
   - Soporte para estaciones `TENG` y `FERR`.

---

## 🛠️ Modificaciones de Código y Refactorización

### 1. Cliente InfluxDB y Publicador MQTT (`services/event-analyzer/src/core/influx_client.py`)
- Implementada la clase `InfluxEventsClient`:
  - `get_recorded_dates()`: Consulta ultrarrápida de fechas únicas UTC en InfluxDB.
  - `get_events_by_date(target_date)`: Consulta Flux consolidando eventos con jerarquía de prioridad:
    $$\text{confirmed / discarded} > \text{manual} > \text{auto}$$
  - `publish_classification(event_id, new_type, current_event)`: Emite el payload JSON con `timestamp_utc` original y QoS 1. Client ID único generado con `uuid.uuid4().hex[:6]`.

### 2. Búsqueda Selectiva y Normalización de Estaciones (`services/event-analyzer/src/core/reader.py`)
- Añadido método `_normalize_station_variants()` que mapea automáticamente nombres de estaciones (ej. `CHA2` $\leftrightarrow$ `CHA02`, `DEV0` $\leftrightarrow$ `DEV00`, `PRM1` $\leftrightarrow$ `PRM01`).
- `scan_event()` resuelve trazas MiniSEED en ventana de 120s alrededor de la fecha del evento sin escanear el histórico completo.

### 3. Interfaz de Usuario y Catálogo Rápido (`services/event-analyzer/app.py`)
- El catálogo y calendario leen **exclusivamente de InfluxDB** en milisegundos.
- Botón **"🔄 Recargar Catálogo"** limpia la caché `@st.cache_data` y re-consulta InfluxDB instantáneamente sin tocar disco.
- Menú de selección con `format_func` sobre IDs inmutables (`event_ids_list`), evitando que Streamlit pierda el evento activo al cambiar el estado.
- Botones interactivos **"✅ Confirmar Evento"** y **"❌ Descartar Evento"** con actualización optimista y notificación Toast.

---

## 📋 Pasos Sugeridos para el Siguiente Agente

1. **Fase 5 — Protocolo de Respaldo y Recuperación (`scripts/db_sync/`)**:
   - Crear el directorio `scripts/db_sync/`.
   - Desarrollar `backup_events.sh` para volcar el bucket `rsa_events` de InfluxDB a disco y sincronizar el archivo comprimido a Google Drive con `rclone`.
   - Desarrollar `restore_events.sh` para restaurar el bucket desde el respaldo en Google Drive en caso de contingencia o sincronización con el home-server.
2. **Script de Backfill Histórico**:
   - Crear un script puntual (`scripts/db_sync/backfill_historical_events.py`) que escanee una sola vez los ~2,324 eventos históricos existentes en `/home/rsa/datos_estaciones_drive` e inserte sus metadatos en InfluxDB (`rsa_events`), dejándolos indexados de forma homogénea.
