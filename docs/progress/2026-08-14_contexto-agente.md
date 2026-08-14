# Resumen de Sesión: Revisión Crítica y Refactorización del Plan de Centralización InfluxDB-MQTT

**Fecha**: 2026-08-14  
**Repositorio**: `RSA-Intern-TIG-MQTT`  
**Agente de IA**: Antigravity (Google DeepMind)  
**Usuario**: Milton / RSA  

---

## 🎯 Objetivo de la Sesión

Realizar un análisis crítico exhaustivo y refactorizar en profundidad el plan de implementación de la arquitectura de sincronización híbrida (Event-Driven + Backups Nativos) documentado en `2026-08-13_influx_sync_implementation_plan.md`. El propósito fue subsanar vacíos de diseño técnico, explicitar los esquemas de datos en InfluxDB, definir el payload MQTT, proteger la funcionalidad de lectura MiniSEED con ObsPy en `Event Analyzer`, y contemplar la coexistencia transitoria de Node-RED con miras a su migración final.

---

## 📂 Estructura del Repositorio Implementada

```text
montajes/server-ubuntu/rsa/RSA-Intern-TIG-MQTT/
├── docs/
│   ├── blueprints/
│   │   └── 2026-08-13_influx_sync_implementation_plan.md   [MODIFICADO] Reescritura técnica completa y detallada
│   └── progress/
│       └── 2026-08-14_contexto-agente.md                   [NUEVO] Este documento de transición técnica
```

---

## ⚙️ Configuración y Prerequisitos de Infraestructura Identificados

1. **Broker Mosquitto (VPS)**:
   * Debe configurarse con persistencia habilitada (`persistence true`, `persistence_location /mosquitto/data/`, `max_queued_messages 0`, `persistent_client_expiration 7d`) para soportar sesiones persistentes (`persistent_session = true`) con QoS 1 en Telegraf ante cortes de energía en el servidor de la oficina o home-server.
2. **Herramientas de Servidor y Contenedores**:
   * Requiere `rclone` configurado con el remote de Google Drive en ambos servidores para el flujo de respaldo manual.
   * La CLI `influx` debe estar disponible en el contenedor `rsa-influxdb` para la gestión de buckets y snapshots.

---

## 🛠️ Modificaciones de Código y Refactorización del Plan

### 1. Fase 1: Esquema de Datos y Bucket Dedicado en InfluxDB
* **Definición del Measurement `seismic_event`**:
  * **Tags (indexados)**: `event_type` (`auto`, `manual`, `confirmed`, `discarded`), `source` (`correlator`, `nodered`, `event_analyzer`), `event_id`.
  * **Fields (no indexados)**: `stations` (string CSV), `n_stations` (integer), `duration_s` (float), `request_id` (string), `details` (JSON string).
* **Bucket `rsa_events`**:
  * Política de retención infinita (`-r 0`) a diferencia del bucket `telemetry` (`90d`).
  * Reutilización del `INFLUXDB_TOKEN` de admin para simplicidad operativa en red local.
* **Convención de Identificadores**: Se preserva la diferenciación por prefijos: `corr-` (automático correlador), `EVT-` (agrupador Streamlit), `man-` (extracción manual).

### 2. Fase 2: Publicación de Metadatos y Coexistencia con Node-RED
* **Payload JSON Estandarizado**: Emisión desde el correlador al tópico `rsa/seismic/smart/events/metadata` con `stations` en formato CSV string (`"CHA1,CHA2,DEV0"`) para compatibilidad nativa directa con Telegraf `json_v2`.
* **Estrategia Transitoria para Eventos Tipo 2 (Node-RED)**:
  * Se acordó mantener operativo Node-RED de forma transitoria publicando al tópico de metadatos (`event_type: "manual"`, `source: "nodered"`).
  * Se establece la meta de retirar Node-RED a futuro una vez que el Event Analyzer incorpore la capacidad de disparo de extracciones manuales.

### 3. Fase 3: Ingesta en Tiempo Real y Tolerancia a Cortes con Telegraf
* **Segmentación de Outputs en `telegraf.conf`**: Configuración de filtros `nameexclude = ["seismic_event"]` para el bucket `telemetry` y `namepass = ["seismic_event"]` para `rsa_events`.
* **Parseo Estricto `json_v2`**: Mapeo explícito de campos y tipos JSON a Tags y Fields de InfluxDB.
* **Sesiones Persistentes**: Uso de `qos = 1` y `client_id` estático (`telegraf-events-oficina` / `telegraf-events-home`).

### 4. Fase 4: Integración Event Analyzer y Preservación de `reader.py`
* **Corrección Crítica**: InfluxDB **no** sustituye al módulo `reader.py`. InfluxDB actúa como índice rápido para poblar el calendario y consultar metadatos instantáneamente, pero `reader.py` y `event_grouper.py` se mantienen para resolver y leer los archivos físicos `.mseed` desde Google Drive bajo demanda (*Lazy Loading*) cuando el usuario solicita visualizar formas de onda con ObsPy.
* **Ciclo Cerrado de Clasificación**: Adición de botones "Confirmar Evento" (Tipo 3) y "Descartar Evento" (Tipo 4) que publican a MQTT, junto con confirmación optimista en `st.session_state` para mitigar la latencia de flush de Telegraf (1-3s).
* **Nuevas Dependencias y Variables**: Adición de `influxdb-client>=1.36.0` y `paho-mqtt>=1.6.1` en `requirements.txt` y parametrización de variables en `docker-compose.yml`.

### 5. Fase 5: Protocolo de Backup / Restore Seguro en Drive
* **Manejo de Restricciones InfluxDB 2.x**: Documentación del flujo real donde `influx restore` no sobreescribe buckets homónimos, requiriendo el borrado previo (`influx bucket delete`) antes de recrear desde el `.tar.gz` descargado por `rclone`.

### 6. Backfill de Eventos Históricos (Decisión Planteada)
* Se formuló la propuesta de ejecutar un script de migración tras la Fase 3 para cargar los ~2,324 eventos históricos existentes en Drive hacia InfluxDB.

---

## 📋 Pasos Sugeridos para el Siguiente Agente

1. **Ejecutar la Fase 1 del Plan**:
   * Crear el bucket `rsa_events` con retención `0` dentro del contenedor `rsa-influxdb` (`docker exec rsa-influxdb influx bucket create -n rsa_events -o rsa -r 0`).
   * Validar con el registro de prueba y consulta Flux indicada en el Checkpoint 1.
2. **Ejecutar la Fase 2 del Plan**:
   * Modificar `scripts/correlator/config.json` para agregar el tópico `events_metadata`.
   * Actualizar `scripts/correlator/regional_event_correlator.py` para publicar el payload JSON de metadatos al confirmar un evento regional.
   * Proporcionar al usuario los comandos `mosquitto_pub` y `mosquitto_sub` para verificar el Checkpoint 2.
3. **Ejecutar la Fase 3 del Plan**:
   * Limpiar y actualizar `services/docker-unified/telegraf.conf` agregando `inputs.mqtt_consumer` (`json_v2`) y los outputs correspondientes.
   * Realizar la prueba de resiliencia deteniendo y reiniciando Telegraf ante mensajes encolados en Mosquitto.
4. **Ejecutar la Fase 4 y 5**:
   * Modificar `services/event-analyzer/` (`requirements.txt`, `docker-compose.yml`, `src/core/influx_client.py` y `app.py`).
   * Crear los scripts `backup_events.sh` y `restore_events.sh` en `scripts/db_sync/`.
