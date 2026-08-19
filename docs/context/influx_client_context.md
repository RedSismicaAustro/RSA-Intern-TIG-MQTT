---
proyecto: RSA-Intern-TIG-MQTT
tipo: contexto_tecnico
archivo: services/event-analyzer/src/core/influx_client.py
temas: [influxdb, flux, paho-mqtt, event-analyzer, clasificacion, metadata, qos1]
---
# Cliente InfluxDB y Publicador MQTT de Eventos Sísmicos — Contexto para Agentes IA

> Módulo central de interoperabilidad de datos para el Event Analyzer. Encapsula las consultas analíticas en lenguaje Flux sobre el bucket `rsa_events` de InfluxDB y la publicación asíncrona de reclasificaciones (confirmado / descartado) al broker MQTT con QoS 1.

**Ruta**: `services/event-analyzer/src/core/influx_client.py`  
**Rutas Asociadas**:
- Aplicación Principal: `services/event-analyzer/app.py`
- Consumidor Telegraf: `services/docker-unified/telegraf.conf`
- Esquema de InfluxDB: Bucket `rsa_events`, Measurement `seismic_event`

**LOC**: 180 | **Lenguaje**: Python 3.11 | **Dependencias**: `influxdb-client>=1.36.0`, `paho-mqtt>=1.6.1`  
**Proceso**: Utilizado como biblioteca interna por el servicio `rsa-event-analyzer` en Streamlit.

---

## 🎯 Arquitectura y Responsabilidades

1. **Consulta de Fechas Disponibles (`get_recorded_dates()`)**:
   - Ejecuta una consulta Flux ultraligera filtrando únicamente la columna `_time` donde `_measurement == "seismic_event"` y `_field == "stations"`.
   - Retorna una lista ordenada de objetos `datetime.date` en tiempo UTC, permitiendo poblar instantáneamente el calendario de Streamlit sin tocar el almacenamiento en disco.
2. **Consulta y Consolidación de Eventos por Día (`get_events_by_date(target_date)`)**:
   - Consulta el rango $[T_{00:00:00Z}, T_{23:59:59Z}]$ aplicando `pivot(rowKey: ["_time", "event_id"], columnKey: ["_field"], valueColumn: "_value")`.
   - Implementa una **jerarquía de prioridad de estados**:
     $$\text{confirmed / discarded (3)} > \text{manual (2)} > \text{auto (1)}$$
     Garantiza que cuando un evento haya sido clasificado manualmente por el operador, prevalezca el estado más reciente sobre la detección automática original.
3. **Publicación de Clasificaciones (`publish_classification(event_id, new_type, current_event)`)**:
   - Emite el mensaje JSON de reclasificación con `event_type: "confirmed"` (Tipo 3) o `"discarded"` (Tipo 4) al tópico `rsa/seismic/smart/events/metadata` con QoS 1.
   - **Preservación Temporal Crítica**: Inyecta en el campo `timestamp_utc` la hora de referencia original del evento sísmico para que Telegraf persista la actualización en el mismo `_time` dentro de InfluxDB, evitando saltos de fecha u hora.
   - Genera IDs de cliente MQTT únicos con `uuid.uuid4().hex[:6]` para evitar colisiones en Mosquitto.

```mermaid
graph LR
    subgraph Streamlit App
        App[app.py] -->|1. get_events_by_date| Client[InfluxEventsClient]
        App -->|2. publish_classification| Client
    end

    subgraph InfluxDB (rsa_events)
        Client -->|Consulta Flux pivot| Bucket[(seismic_event)]
    end

    subgraph MQTT / Telegraf Loop
        Client -->|Publica QoS 1 events/metadata| Broker[Mosquitto]
        Broker -->|Consume json_v2| Telegraf[rsa-telegraf]
        Telegraf -->|timestamp_path: timestamp_utc| Bucket
    end
```

---

## ⚙️ Variables de Entorno Utilizadas

- `INFLUXDB_URL`: URL del servidor InfluxDB (por defecto `http://influxdb:8086`).
- `INFLUXDB_TOKEN`: Token de autenticación de InfluxDB v2.
- `INFLUXDB_ORG`: Organización de InfluxDB (`rsa`).
- `INFLUXDB_EVENTS_BUCKET`: Nombre del bucket de eventos (`rsa_events`).
- `MQTT_BROKER`: Dirección IP / Host del broker Mosquitto.
- `MQTT_PORT`: Puerto MQTT (por defecto `1883`).
- `MQTT_USERNAME` / `MQTT_PASSWORD`: Credenciales del usuario MQTT.
- `MQTT_METADATA_TOPIC`: Tópico central de metadatos (`rsa/seismic/smart/events/metadata`).

---

## 🛠️ Métodos Principales

| Método | Argumentos | Retorno | Descripción |
|--------|------------|---------|-------------|
| `ping()` | Ninguno | `bool` | Comprueba si el servidor InfluxDB está online y accesible. |
| `get_recorded_dates()` | Ninguno | `List[date]` | Retorna fechas UTC únicas con eventos registrados. |
| `get_events_by_date()` | `target_date: date` | `List[Dict]` | Retorna todos los eventos del día consolidando clasificaciones por prioridad. |
| `publish_classification()` | `event_id, new_type, current_event` | `Tuple[bool, str]` | Publica la actualización de estado a MQTT con QoS 1. |
