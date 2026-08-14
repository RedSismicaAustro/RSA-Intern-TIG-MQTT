# Plan de Implementación: Centralización y Sincronización InfluxDB-MQTT

**Fecha**: 2026-08-13  
**Última revisión**: 2026-08-14  
**Documento**: Plan de Acción por Fases  
**Objetivo**: Implementar la arquitectura de sincronización híbrida (Event-Driven + Backups nativos) para el registro y clasificación de 4 tipos de eventos sísmicos entre la Oficina RSA y el Home-Server.

---

## 📋 Prerequisitos Generales

Antes de iniciar cualquier fase de desarrollo, se deben verificar y asegurar las siguientes condiciones en la infraestructura existente:

### Mosquitto (VPS - Broker MQTT)
Verificar que el archivo de configuración de Mosquitto en el VPS tiene habilitada la persistencia de mensajes para soportar sesiones persistentes de clientes (Telegraf):

```conf
# /mosquitto/config/mosquitto.conf (dentro del contenedor del VPS)
persistence true
persistence_location /mosquitto/data/
max_queued_messages 0          # 0 = sin límite (seguro para metadatos de baja frecuencia)
persistent_client_expiration 7d # Expira clientes inactivos tras 7 días
```

> **Nota**: `max_queued_messages 0` es seguro porque los eventos sísmicos son de baja frecuencia (unas pocas decenas al día como máximo). Mosquitto solo retendrá payloads JSON livianos (~500 bytes cada uno).

### Herramientas en Servidores (Oficina y Home-Server)
* `rclone` instalado y configurado con el remote de Google Drive en ambas máquinas.
* Acceso a la CLI de InfluxDB (`influx`) disponible dentro del contenedor `rsa-influxdb`.

---

## 🛠️ Fase 1: Diseño del Esquema de Datos y Configuración Base

**Objetivo**: Definir la estructura de la base de datos temporal, crear el bucket dedicado y verificar que responde a consultas Flux.

### Esquema de Datos

| Elemento | Nombre | Tipo | Descripción |
|----------|--------|------|-------------|
| **Measurement** | `seismic_event` | — | Registro de un evento sísmico |
| **Tag** | `event_type` | string | `auto`, `manual`, `confirmed`, `discarded` |
| **Tag** | `source` | string | Origen: `correlator`, `nodered`, `event_analyzer` |
| **Tag** | `event_id` | string | ID único (ej. `corr-20260721-225225` o `EVT-20260721-225225`) |
| **Field** | `stations` | string | Lista CSV de estaciones (ej. `"CHA1,CHA2,DEV0"`) |
| **Field** | `n_stations` | integer | Cantidad de estaciones involucradas |
| **Field** | `duration_s` | float | Duración del recorte en segundos |
| **Field** | `request_id` | string | ID de la solicitud de extracción broadcast |
| **Field** | `details` | string | JSON serializado con metadatos adicionales (probabilidades, fases, etc.) |
| **Timestamp** | — | nanoseconds | Hora UTC del evento |

> **Justificación**: `event_type`, `source` y `event_id` son Tags (indexados) para permitir consultas Flux eficientes con `filter()`. Los campos como `stations` son Fields porque su cardinalidad es alta y variable.

### Convención de `event_id`
Se mantienen ambos formatos existentes, diferenciados por prefijo:
* **Correlador**: `corr-YYYYMMDD-HHMMSS` (generado por `regional_event_correlator.py`).
* **Event Analyzer**: `EVT-YYYYMMDD-HHMMSS` (generado por `event_grouper.py`).
* **Node-RED (manual)**: `man-YYYYMMDD-HHMMSS` (generado al publicar desde Node-RED).

### Acciones
1. Crear el bucket `rsa_events` con retención infinita (`0`) mediante la UI web de InfluxDB o ejecutando dentro del contenedor:
   ```bash
   docker exec rsa-influxdb influx bucket create -n rsa_events -o rsa -r 0
   ```
2. Reutilizar el token de admin existente (`INFLUXDB_TOKEN` en `.env`) para Telegraf y Streamlit. En un entorno de red interna, un token dedicado es innecesario.

### Comprobación (Checkpoint 1)
* Escribir manualmente un registro de prueba usando la interfaz web de InfluxDB (Data Explorer) o la API REST:
  ```bash
  docker exec rsa-influxdb influx write \
    --bucket rsa_events \
    --org rsa \
    'seismic_event,event_type=auto,source=correlator,event_id=test-20260814-120000 stations="CHA1,CHA2",n_stations=2i,duration_s=120.0,request_id="test-req-001",details="{}" 1723636800000000000'
  ```
* Verificar la inserción con una consulta Flux en Data Explorer:
  ```flux
  from(bucket: "rsa_events")
    |> range(start: -1h)
    |> filter(fn: (r) => r._measurement == "seismic_event")
  ```
* Confirmar que Tags y Fields aparecen con los tipos correctos. Borrar el registro de prueba.

---

## 📡 Fase 2: Adaptación del Correlador Regional (Publicador MQTT)

**Objetivo**: Hacer que el correlador publique los metadatos del evento confirmado al broker central en un tópico dedicado para su ingesta en InfluxDB.

### Estructura del Payload JSON

```json
{
  "event_type": "auto",
  "source": "correlator",
  "event_id": "corr-20260721-225225",
  "timestamp_utc": "2026-07-21T22:52:25.000Z",
  "stations": ["CHA1", "CHA2", "DEV0"],
  "n_stations": 3,
  "duration_s": 120.0,
  "request_id": "corr-20260721-225225",
  "trigger_details": {
    "window_s": 10.0,
    "detections": [
      {"station": "CHA2", "phase": "P", "probability": 0.92, "timestamp": "2026-07-21T22:52:14.123Z"},
      {"station": "DEV0", "phase": "P", "probability": 0.87, "timestamp": "2026-07-21T22:52:21.456Z"}
    ]
  }
}
```

### Acciones
1. Agregar el nuevo tópico al archivo `scripts/correlator/config.json`:
   ```json
   "topics": {
     "events_subscription": "{org}/{app}/{cap}/+/events/detected",
     "events_metadata": "{org}/{app}/{cap}/events/metadata",
     "cmd_broadcast": "{org}/{app}/{cap}/broadcast/cmd/extract_event",
     "cmd_response_sub": "{org}/{app}/{cap}/+/cmd/extract_event/res"
   }
   ```
2. Modificar `regional_event_correlator.py`:
   - En `__init__()`: cargar el nuevo tópico `self.topic_metadata`.
   - En `_disparar_extraccion_broadcast()`: después de publicar el comando broadcast, construir y publicar el payload de metadatos al tópico `events/metadata` con QoS 1.
3. Serializar `trigger_details` como JSON string en el campo `details` para compatibilidad con el esquema de InfluxDB.

### Manejo Transitorio de Eventos Tipo 2 (Node-RED)
Node-RED se mantendrá operativo durante esta fase de transición, pero con miras a su retirada futura a favor de un sistema centralizado en Event Analyzer. Para registrar los eventos manuales Tipo 2:
* Configurar un nodo `mqtt out` en Node-RED que publique al mismo tópico `rsa/seismic/smart/events/metadata` con `event_type: "manual"` y `source: "nodered"`.
* Cuando se implemente la funcionalidad equivalente en Event Analyzer (Fase 4), se migrará el flujo y se retirará Node-RED.

### Comprobación (Checkpoint 2)
* Publicar manualmente un JSON de alerta falsa desde la terminal del usuario (no desde el agente, por restricción SSHFS):
  ```bash
  # Simular detección de estación TEST01
  mosquitto_pub -h <BROKER_IP> -u <USER> -P <PASS> -t "rsa/seismic/smart/TEST01/events/detected" \
    -m '{"station_id":"TEST01","timestamp":"2026-08-14T12:00:00.000Z","type":"P","probability":0.95}'
  # Simular detección de estación TEST02 (dentro de 10s)
  mosquitto_pub -h <BROKER_IP> -u <USER> -P <PASS> -t "rsa/seismic/smart/TEST02/events/detected" \
    -m '{"station_id":"TEST02","timestamp":"2026-08-14T12:00:05.000Z","type":"P","probability":0.88}'
  ```
* Verificar con `mosquitto_sub` que el correlador publica el JSON de metadatos en `rsa/seismic/smart/events/metadata`:
  ```bash
  mosquitto_sub -h <BROKER_IP> -u <USER> -P <PASS> -t "rsa/seismic/smart/events/metadata" -v
  ```
* Confirmar que la estructura del JSON recibido coincide con el esquema de la Fase 1.

---

## 🔌 Fase 3: Integración de Ingesta en Tiempo Real (Telegraf)

**Objetivo**: Automatizar la escritura a InfluxDB desde MQTT y configurar la tolerancia a fallos por cortes cortos mediante sesiones persistentes.

### Acciones
1. **Limpiar `telegraf.conf`**: El archivo actual (`services/docker-unified/telegraf.conf`) pesa ~562 KB y es probablemente el archivo de ejemplo por defecto. Antes de agregar la sección MQTT, verificar qué plugins están activos y eliminar las secciones comentadas innecesarias o crear un archivo limpio dedicado.
2. **Agregar `inputs.mqtt_consumer`** configurado para el tópico de metadatos:
   ```toml
   [[inputs.mqtt_consumer]]
     servers = ["tcp://${MQTT_BROKER}:1883"]
     topics = ["rsa/seismic/smart/events/metadata"]
     username = "${MQTT_USERNAME}"
     password = "${MQTT_PASSWORD}"
     qos = 1
     persistent_session = true
     client_id = "telegraf-events-oficina"  # Cambiar a "telegraf-events-home" en el home-server
     data_format = "json_v2"
     
     # Nombre del measurement de destino
     [inputs.mqtt_consumer.tags]
       # Tags vacíos aquí; se extraen del JSON
     
     [[inputs.mqtt_consumer.json_v2]]
       [[inputs.mqtt_consumer.json_v2.tag]]
         path = "event_type"
       [[inputs.mqtt_consumer.json_v2.tag]]
         path = "source"
       [[inputs.mqtt_consumer.json_v2.tag]]
         path = "event_id"
       [[inputs.mqtt_consumer.json_v2.field]]
         path = "n_stations"
         type = "int"
       [[inputs.mqtt_consumer.json_v2.field]]
         path = "duration_s"
         type = "float"
       [[inputs.mqtt_consumer.json_v2.field]]
         path = "request_id"
         type = "string"
       [[inputs.mqtt_consumer.json_v2.field]]
         path = "trigger_details"
         type = "string"
         # Se serializa el objeto completo como JSON string para el campo "details"
   ```
   > **Nota sobre `stations`**: El campo `stations` del JSON es un array (`["CHA1","CHA2"]`). Telegraf `json_v2` no convierte arrays a CSV automáticamente. Se necesitará que el correlador publique `stations` ya como CSV string (`"CHA1,CHA2"`) en lugar de array JSON, o usar un procesador `starlark` para la conversión.

3. **Configurar output dedicado para el bucket `rsa_events`** usando `namepass` para separarlo de la telemetría existente:
   ```toml
   # Output existente para telemetría
   [[outputs.influxdb_v2]]
     urls = ["${INFLUXDB_URL}"]
     token = "${INFLUXDB_TOKEN}"
     organization = "${INFLUXDB_ORG}"
     bucket = "${INFLUXDB_BUCKET}"        # "telemetry"
     namepass = ["cpu", "mem", "disk", "mqtt_consumer"]  # métricas de sistema
   
   # Output dedicado para eventos sísmicos
   [[outputs.influxdb_v2]]
     urls = ["${INFLUXDB_URL}"]
     token = "${INFLUXDB_TOKEN}"
     organization = "${INFLUXDB_ORG}"
     bucket = "rsa_events"
     namepass = ["seismic_event"]          # solo el measurement de eventos
   ```
   > **Alternativa más simple**: Si el Telegraf actual no está procesando telemetría de sistema, se puede usar un solo output apuntando directamente a `rsa_events` y evitar la complejidad de `namepass`.

4. **Agregar variable de entorno** `INFLUXDB_EVENTS_BUCKET=rsa_events` al `.env.example` y al servicio `telegraf` en `docker-compose.yml` (si se decide parametrizar en lugar de hardcodear).

### Comprobación (Checkpoint 3)
* Publicar un mensaje JSON simulado al tópico MQTT desde la terminal del usuario:
  ```bash
  mosquitto_pub -h <BROKER_IP> -u <USER> -P <PASS> \
    -t "rsa/seismic/smart/events/metadata" \
    -m '{"event_type":"auto","source":"correlator","event_id":"test-chk3","timestamp_utc":"2026-08-14T12:00:00Z","stations":"CHA1,CHA2","n_stations":2,"duration_s":120.0,"request_id":"test-req","trigger_details":"{}"}'
  ```
* Validar en el Data Explorer de InfluxDB (`http://<IP>:8086`) que el dato aparece en el bucket `rsa_events` con los Tags y Fields correctos.
* **Prueba de Resiliencia**:
  1. Detener el contenedor de Telegraf: `docker stop rsa-telegraf`
  2. Publicar 3 eventos de prueba distintos al tópico MQTT.
  3. Reiniciar Telegraf: `docker start rsa-telegraf`
  4. Comprobar que los 3 eventos atrasados se ingestan en cascada gracias a la sesión persistente de Mosquitto.

---

## 🖥️ Fase 4: Integración de Event Analyzer con InfluxDB y MQTT (Lectura/Escritura)

**Objetivo**: Complementar Streamlit con InfluxDB para el índice rápido de eventos y cerrar el ciclo de retroalimentación (clasificación de eventos Tipo 3 y 4).

> **Corrección importante**: El motor Regex de `reader.py` **NO se sustituye**. InfluxDB almacena metadatos de eventos pero no las rutas a los archivos `.mseed`. `reader.py` sigue siendo necesario para localizar y cargar los archivos MiniSEED desde Google Drive cuando el usuario selecciona un evento para visualizar ondas. Lo que se hace es **complementar**: InfluxDB provee el índice rápido para el calendario, y `reader.py` resuelve los archivos bajo demanda.

### Acciones
1. **Agregar dependencias** a `services/event-analyzer/requirements.txt`:
   ```
   influxdb-client>=1.36.0
   paho-mqtt>=1.6.1
   ```
2. **Agregar variables de entorno** al servicio `event-analyzer` en `docker-compose.yml`:
   ```yaml
   environment:
     - DATA_DIR=/data/events
     - TZ=America/Guayaquil
     - RESAMPLER_HOST=${RESAMPLER_HOST:-ubuntu-server}
     # --- Nuevas variables para InfluxDB ---
     - INFLUXDB_URL=http://influxdb:8086
     - INFLUXDB_TOKEN=${INFLUXDB_TOKEN}
     - INFLUXDB_ORG=${INFLUXDB_ORG}
     - INFLUXDB_EVENTS_BUCKET=rsa_events
     # --- Nuevas variables para MQTT ---
     - MQTT_BROKER=${MQTT_BROKER}
     - MQTT_USERNAME=${MQTT_USERNAME}
     - MQTT_PASSWORD=${MQTT_PASSWORD}
   ```
3. **Crear módulo `src/core/influx_client.py`**: Encapsular las consultas Flux y la conexión al bucket `rsa_events`. Exponer métodos como:
   - `query_events_by_date(date) -> list[dict]`: Para poblar el calendario y el desplegable.
   - `query_event_metadata(event_id) -> dict`: Para enriquecer la sección "Ver Metadatos del Evento".
4. **Modificar `app.py`**:
   - Usar `influx_client.query_events_by_date()` para generar el índice del calendario (reemplaza el escaneo lento de disco en el arranque).
   - Mantener la llamada a `reader.py` y `event_grouper.py` solo cuando el usuario confirma la selección de un evento para visualización de ondas (Lazy Loading existente).
   - Agregar botones **"✅ Confirmar Evento"** (Tipo 3) y **"❌ Descartar Evento"** (Tipo 4).
   - Al hacer clic, publicar un JSON al tópico `rsa/seismic/smart/events/metadata` con el `event_type` correspondiente y `source: "event_analyzer"`.
5. **Latencia del viaje ida y vuelta (MQTT → Telegraf → InfluxDB)**: El flush de Telegraf introduce un retardo de 1-3 segundos. Implementar confirmación optimista en `st.session_state` (mostrar el cambio de estado inmediatamente en la UI) mientras los datos persisten en segundo plano.
6. **Node-RED (transitorio)**: Mientras Node-RED siga operativo, las extracciones manuales se registrarán publicando al tópico `events/metadata` con `event_type: "manual"` y `source: "nodered"`. Una vez que Event Analyzer absorba esta funcionalidad, se retirará Node-RED.

### Comprobación (Checkpoint 4)
* Reconstruir el contenedor: `docker compose up -d --build event-analyzer`.
* Cargar Streamlit en `http://<IP>:8501` y comprobar que el calendario se pobla instantáneamente desde InfluxDB (sin el spinner de "Parseando metadatos...").
* Seleccionar un evento existente (Tipo 1 `auto`), visualizar las ondas (confirmar que `reader.py` sigue funcionando), y pulsar "Descartar Evento" (Tipo 4).
* Recargar la página y verificar que el estado actualizado (`discarded`) se refleja en los metadatos del evento (viaje completo: MQTT → Telegraf → InfluxDB → Streamlit).

---

## 💾 Fase 5: Protocolo Manual de Backups (Cortes Largos / Home-Server)

**Objetivo**: Proveer un método seguro de sincronización masiva a través de Google Drive evitando la corrupción del motor de InfluxDB.

### Consideraciones Técnicas
* `influx backup` genera un **snapshot completo** del bucket (no incremental). Para el caso de uso actual (solo metadatos de eventos, ~500 bytes por registro), el tamaño será de pocos MB incluso tras años de operación, por lo que esto no es una limitación práctica.
* `influx restore` en InfluxDB 2.x **no puede sobreescribir un bucket existente** con el mismo nombre. El flujo correcto es: borrar el bucket → restaurar desde backup (que lo recrea).

### Convención de Ruta en Google Drive
Los backups se almacenarán en: `RSA-Backups/influxdb/rsa_events_YYYY-MM-DD.tar.gz`

### Acciones
1. **Crear script `scripts/db_sync/backup_events.sh`**:
   - Ejecuta `influx backup` dentro del contenedor `rsa-influxdb` apuntando al bucket `rsa_events`.
   - Empaqueta el resultado en `.tar.gz` con la convención de nombre definida.
   - Sube el archivo a Google Drive usando `rclone copy`.
2. **Crear script `scripts/db_sync/restore_events.sh`**:
   - Descarga el último `.tar.gz` de Drive usando `rclone copy`.
   - Extrae el contenido.
   - **Borra** el bucket `rsa_events` existente: `influx bucket delete -n rsa_events -o rsa`.
   - Ejecuta `influx restore` que recrea el bucket desde el backup.
   - Verifica la integridad con una consulta Flux de conteo.

### Comprobación (Checkpoint 5)
* Generar un backup desde el servidor de la oficina ejecutando `backup_events.sh`.
* Verificar que el archivo `.tar.gz` aparece en `RSA-Backups/influxdb/` en Google Drive.
* En el home-server (o simulando localmente):
  1. Borrar intencionadamente el bucket `rsa_events`.
  2. Ejecutar `restore_events.sh`.
  3. Verificar que todos los registros regresan íntegros mediante una consulta Flux de conteo y comparación contra el total conocido.

---

## 📊 Decisión Pendiente: Backfill de Eventos Históricos

El Event Analyzer ya tiene indexados ~2,324 eventos regionales por escaneo regex de Google Drive. Estos datos **no existirán** en InfluxDB porque la base de datos de eventos se está creando desde cero.

### Opciones
* **Opción A (Recomendada)**: Crear un script de migración que escanee Drive usando `reader.py` + `event_grouper.py`, construya los payloads y los inserte directamente vía API de InfluxDB. Esto permite que el calendario de Streamlit muestre el historial completo desde el día 1.
* **Opción B**: Aceptar que solo los eventos futuros se registrarán en InfluxDB. El calendario mostraría datos solo desde la fecha de implementación. Los eventos históricos seguirían accesibles por el método actual de escaneo de Drive.

> Esta decisión se tomará al finalizar la Fase 3, cuando la infraestructura de ingesta ya esté validada.

---

## 🗺️ Diagrama General de la Arquitectura

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         VPS (Broker MQTT)                              │
│                        Mosquitto + Persistencia                        │
│                     rsa/seismic/smart/events/metadata                  │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                  ┌────────────┼────────────┐
                  │ (QoS 1)    │ (QoS 1)    │ (QoS 1)
                  ▼            ▼            ▼
          ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
          │ Publicadores │ │  Telegraf    │ │  Telegraf    │
          │              │ │  (Oficina)   │ │ (Home-Srv)   │
          │ • Correlador │ │  persistent  │ │  persistent  │
          │   (Tipo 1)   │ │  session     │ │  session     │
          │ • Node-RED   │ └──────┬───────┘ └──────┬───────┘
          │   (Tipo 2)   │        │                │
          │ • Streamlit  │        ▼                ▼
          │   (Tipo 3/4) │ ┌──────────────┐ ┌──────────────┐
          └──────────────┘ │  InfluxDB    │ │  InfluxDB    │
                           │  (Oficina)   │ │ (Home-Srv)   │
                           │  rsa_events  │ │  rsa_events  │
                           └──────┬───────┘ └──────┬───────┘
                                  │                │
                                  ▼                ▼
                           ┌──────────────┐ ┌──────────────┐
                           │  Streamlit   │ │  Streamlit   │
                           │  Event       │ │  Event       │
                           │  Analyzer    │ │  Analyzer    │
                           │  :8501       │ │  :8501       │
                           └──────────────┘ └──────────────┘

               ┌─────────────────────────────────────────┐
               │  Sincronización para cortes largos:     │
               │  backup_events.sh → Google Drive →      │
               │  → restore_events.sh                    │
               └─────────────────────────────────────────┘
```
