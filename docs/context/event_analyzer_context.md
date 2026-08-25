---
proyecto: RSA-Intern-TIG-MQTT
tipo: contexto_tecnico
archivo: services/event-analyzer/app.py
temas: [streamlit, obspy, plotly, event-analyzer, miniseed, docker-compose, dsp, lazy-loading, influxdb, mqtt, clasificacion, adr-016]
generado: 2026-08-25
---
# Visualizador Web de Eventos Sísmicos (Event Analyzer) — Contexto para Agentes IA

> Aplicación Web modular containerizada en Streamlit + ObsPy + Plotly + InfluxDB + MQTT para la ingesta ultra rápida desde base de datos, alineación temporal UTC, procesamiento DSP, visualización interactiva multiestación y ciclo cerrado de clasificación (confirmación/descarte) de eventos sísmicos.

**Ruta**: `services/event-analyzer/app.py`  
**Rutas de Archivos Asociados**:
- Cliente InfluxDB y MQTT: `services/event-analyzer/src/core/influx_client.py`
- Ingestor y Búsqueda Selectiva: `services/event-analyzer/src/core/reader.py`
- Agrupador Regional UTC: `services/event-analyzer/src/core/event_grouper.py`
- Clase Base Pipeline: `services/event-analyzer/src/modules/base.py`
- Renderizador de Formas de Onda: `services/event-analyzer/src/modules/visualizer.py`
- Utilidades de Tiempo: `services/event-analyzer/src/utils/time_utils.py`
- Tema Visual RSA: `services/event-analyzer/.streamlit/config.toml`
- Dockerfile: `services/event-analyzer/Dockerfile`
- Dependencias: `services/event-analyzer/requirements.txt`
- Integración Docker Compose: `services/docker-unified/docker-compose.yml`

**LOC**: `app.py`: 285 | `influx_client.py`: 180 | `reader.py`: 145 | `event_grouper.py`: 90 | `visualizer.py`: 234 | `base.py`: 20 | `time_utils.py`: 22 | `Dockerfile`: 18  
**Lenguaje/Formato**: Python 3.11, Streamlit UI, TOML, Dockerfile, YAML  
**Dependencias/Librerías**: `obspy>=1.4.0`, `streamlit>=1.30.0`, `plotly>=5.18.0`, `pandas>=2.0.0`, `numpy>=1.24.0`, `plotly-resampler>=0.9.1`, `influxdb-client>=1.36.0`, `paho-mqtt>=1.6.1`  
**Proceso**: Servicio contenedorizado (`rsa-event-analyzer`) expuesto en el puerto `8501` (Streamlit) y `8050` (Resampler Dash), parte del stack `docker-unified` en la red `rsa_network` (`monitoring`).

---

## 🎯 Arquitectura y Flujo de Datos

El sistema opera bajo un modelo desacoplado de índice rápido en InfluxDB y resolución global de trazas bajo demanda (*Lazy Loading*) en Google Drive:

1. **Índice Rápido desde InfluxDB (`influx_client.py`)**:
   - Consulta el bucket `rsa_events` mediante consultas Flux parametrizadas.
   - Obtiene fechas únicas con eventos (`get_recorded_dates()`) y lista de eventos por día (`get_events_by_date()`) en milisegundos, eliminando la sobrecarga de I/O de disco durante la navegación.
   - Aplica jerarquía de prioridades de estado (`confirmed`/`discarded` > `manual` > `auto`) para consolidar actualizaciones de clasificación del mismo evento.
2. **Interfaz de Usuario Streamlit y Estado Optimista (`app.py`)**:
   - Barra lateral con selector de fecha (`st.date_input`) y menú desplegable de eventos con `format_func` sobre IDs inmutables (`event_ids_list`), mostrando indicador `(N det.)` para estaciones detectoras.
   - Insignias visuales de estado: `🤖 Auto` (Correlador), `👤 Manual` (Node-RED), `✅ Confirmado` (Sismo Real), `❌ Descartado` (Falsa Alarma / Ruido).
   - Botón **"🔄 Recargar Catálogo"** que invalida la caché `@st.cache_data` y consulta InfluxDB instantáneamente.
   - Botones de acción **"✅ Confirmar Evento"** y **"❌ Descartar Evento"** con actualización optimista inmediata en `st.session_state` y notificación Toast.
   - Métricas de cabecera que diferencian `📡 Estaciones Resueltas (M/M)` vs `Detectoras: EST1, EST2` (ADR-016).
3. **Ciclo Cerrado de Clasificación MQTT**:
   - Al presionar Confirmar o Descartar, `influx_client.publish_classification()` emite el payload JSON a `rsa/seismic/smart/events/metadata` con QoS 1 conservando el `timestamp_utc` original del evento.
   - Telegraf captura la publicación y actualiza el registro en InfluxDB.
4. **Búsqueda Global y Aislamiento de Registro Continuo (`reader.py`)**:
   - Al seleccionar un evento, `reader.scan_event(ref_time=ref_dt, stations=None, window_s=120.0)` busca en `*/events/*.mseed` (sin recursión), resolviendo trazas de **todas las estaciones** que respondieron al broadcast y aislando los bloques de registro continuo en `/mseed/` (ADR-016).
   - Mapea variantes de código de estación mediante `_normalize_station_variants()` (ej. `CHA2` $\leftrightarrow$ `CHA02`, `DEV0` $\leftrightarrow$ `DEV00`).
5. **Carga Bajo Demanda, DSP y Resampling Dinámico (`visualizer.py`)**:
   - Carga con ObsPy únicamente los archivos MiniSEED resueltos.
   - Aplica remoción de tendencia (`detrend`), filtrado pasabanda Butterworth y envolvente `FigureResampler(port=8050)` para zoom interactivo de alta resolución sin degradar el navegador.
5. **Carga Bajo Demanda, DSP y Resampling Dinámico (`visualizer.py`)**:
   - Carga con ObsPy únicamente los archivos MiniSEED resueltos.
   - Aplica remoción de tendencia (`detrend`), filtrado pasabanda Butterworth y envolvente `FigureResampler(port=8050)` para zoom interactivo de alta resolución sin degradar el navegador.

```mermaid
graph TD
    subgraph InfluxDB Bucket (rsa_events)
        DB[(Índice de Metadatos de Eventos)]
    end

    subgraph Core Streamlit UI (app.py)
        DB -->|1. get_catalog_dates & get_events_by_date| Client[InfluxEventsClient: influx_client.py]
        Client -->|2. Carga Instantánea <50ms| Calendar[Calendario & Selector de Evento]
        Calendar -->|3. Evento Seleccionado| Actions[Botones Confirmar / Descartar]
        Actions -->|4. Publicación QoS 1 MQTT| MQTT[Broker Mosquitto: events/metadata]
    end

    subgraph Google Drive (/data/events)
        DriveFiles[Archivos .mseed en Directorios de Estaciones]
    end

    subgraph Lazy Loading & DSP
        Calendar -->|5. Resolver Solo Evento Actual| Reader[MseedReader.scan_event: reader.py]
        DriveFiles -->|6. Lectura Puntual| Reader
        Reader -->|7. ObsPy Stream Read| Visualizer[WaveformVisualizer: visualizer.py]
        Visualizer -->|8. Detrend + Bandpass + FigureResampler| Plotly[Gráfico Plotly Interactivo :8501 / :8050]
    end
```

---

## ⚙️ Configuraciones y Variables de Entorno

### Variables del Entorno Docker (`docker-compose.yml`)
- `DATA_DIR=/data/events`: Montaje en solo lectura de Google Drive.
- `INFLUXDB_URL=http://influxdb:8086`: Conexión interna a InfluxDB.
- `INFLUXDB_TOKEN=${INFLUXDB_TOKEN}`: Token de autenticación InfluxDB v2.
- `INFLUXDB_ORG=${INFLUXDB_ORG}`: Organización InfluxDB (`rsa`).
- `INFLUXDB_EVENTS_BUCKET=${INFLUXDB_EVENTS_BUCKET:-rsa_events}`: Bucket de eventos sísmicos.
- `MQTT_BROKER=${MQTT_BROKER}`: Host del broker Mosquitto.
- `MQTT_PORT=1883`: Puerto MQTT.
- `MQTT_USERNAME` / `MQTT_PASSWORD`: Credenciales MQTT autenticadas.
- `MQTT_METADATA_TOPIC=rsa/seismic/smart/events/metadata`: Tópico de metadatos.
- `RESAMPLER_HOST=ubuntu-server`: Hostname/IP para callbacks Dash.

### Puertos Expuestos
- `8501:8501`: Interfaz web Streamlit.
- `8050:8050`: Servidor Dash de `plotly-resampler`.

---

## 🛠️ Componentes y Clases Clave

| Clase / Módulo | Archivo | Propósito / Función |
|----------------|---------|---------------------|
| `InfluxEventsClient` | `src/core/influx_client.py` | Consulta Flux de fechas/eventos, jerarquía de estados y publicación MQTT con QoS 1. |
| `MseedReader` | `src/core/reader.py` | Resolución selectiva `scan_event()` con normalización de variantes de estación (`_normalize_station_variants`). |
| `EventFile` | `src/core/reader.py` | DataClass liviana de metadatos de archivo MiniSEED y cargador `load_stream()`. |
| `EventGrouper` | `src/core/event_grouper.py` | Motor de agrupación temporal multiestación (utilizado en modo fallback/offline). |
| `RegionalEvent` | `src/core/event_grouper.py` | Estructura de evento regional con metadatos y métodos de carga ObsPy. |
| `WaveformVisualizer` | `src/modules/visualizer.py` | Procesamiento DSP (detrend, bandpass) y renderizado de alta resolución con `FigureResampler`. |
| `time_utils.py` | `src/utils/time_utils.py` | Formateo UTC y duraciones para la interfaz de usuario. |

---

## 📌 Limitaciones Conocidas y Buenas Prácticas

1. **Persistencia Temporal**: Las clasificaciones publicadas a MQTT deben contener el `timestamp_utc` original del evento para que Telegraf lo almacene en el mismo timestamp `_time` en InfluxDB.
2. **Lazy Loading Puro**: Nunca se debe ejecutar un escaneo recursivo completo de Google Drive durante el ciclo de vida normal de la aplicación para preservar el rendimiento.
