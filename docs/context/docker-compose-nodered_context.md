---
proyecto: RSA-Intern-TIG-MQTT
tipo: contexto_tecnico
archivo: services/node-red/docker-compose.yml
temas: [docker-compose, node-red, automation, panel-control, mqtt, ui-dashboard, influxdb, telegraf]
---
# Docker Compose Node-RED y Archivos Asociados — Contexto para Agentes IA

> Orquestación y lógica del panel de control y automatización remota basado en Node-RED para el envío de comandos de extracción de eventos, registro automático de metadatos en InfluxDB y monitoreo de respuestas de la red acelerográfica.

**Ruta**: `services/node-red/docker-compose.yml`  
**Rutas de Archivos Asociados**:
- Flujos de Node-RED: `services/node-red/flows.json`
- Configuración de Node-RED: `services/node-red/settings.js`
- Dependencias del Panel: `services/node-red/package.json`

**LOC**: `docker-compose.yml`: 20 | `flows.json`: 691 | `settings.js`: 96 | `package.json`: 8  
**Lenguaje/Formato**: YAML (Docker Compose), JSON (Flows & npm Package), JavaScript (CommonJS Settings)  
**Dependencias/Imágenes**: `nodered/node-red:latest` (Imagen Docker) | `node-red-dashboard` (~3.6.6)  
**Proceso**: Contenedor Docker persistente administrado por Docker Compose, integrado en la red externa `rsa_network` para su comunicación.

---

## 🎯 Arquitectura y Flujos de Automatización

El panel de control remoto opera como una consola web interactiva conectada al broker MQTT:

1. **Flujo de Salida Dual (Extracción y Registro de Metadatos)**:
   - El operador selecciona los parámetros en el formulario visual (Estación destinataria: `broadcast`, `DEV00`, `DEV01`, `CHA01`, `CHA02`, `TENG`, `FERR`; Fecha, Hora, Duración y Zona Horaria: UTC-5 / UTC).
   - Al presionar **"Enviar Comando"**, el nodo `Build Command` emite dos mensajes simultáneos:
     1. `rsa/seismic/smart/{target_id}/cmd/extract_event`: Comando de extracción hacia los acelerógrafos con `upload: true` y `delete_after_upload: true`.
     2. `rsa/seismic/smart/events/metadata`: Registro de metadatos con `event_type: "manual"`, `source: "nodered"`, `request_id` y `timestamp_utc` para que Telegraf lo ingeste inmediatamente en InfluxDB (`rsa_events`).
2. **Flujo de Entrada (Recepción y Log de Respuestas)**:
   - Suscrito a `rsa/seismic/smart/+/cmd/extract_event/res` para capturar el estado (`completed`/`error`) de cada estación.
   - Despliega notificaciones toast en la UI y alimenta el historial en memoria `flow.responseHistory`.

```mermaid
graph TD
    subgraph UI Operador (Puerto 1880/ui)
        Form[Formulario de Extracción] -->|Click Enviar| Build[Función: Build Command]
        Toast[Notificación Toast] -.-> UI
        History[Historial Respuestas] -.-> UI
    end

    subgraph Node-RED Engine (flows.json)
        Build -->|1. Comando extract_event| CmdMsg[MQTT Out: cmd/extract_event]
        Build -->|2. Metadatos InfluxDB| MetaMsg[MQTT Out: events/metadata]
        ResIn[MQTT In: cmd/extract_event/res] --> Parse[Función: Parse Response]
        Parse --> Toast
        Parse --> History
    end

    CmdMsg -->|QoS 1| Broker[Mosquitto Broker]
    MetaMsg -->|QoS 1| Broker
    Broker -->|Comando| Estaciones[Acelerógrafos DEV00, CHA01, ...]
    Estaciones -->|Respuestas| Broker
    Broker --> ResIn
    Broker -->|Metadatos| Telegraf[Telegraf -> InfluxDB rsa_events]
```

---

## ⚙️ Configuraciones y Variables de Entorno

### Variables del Entorno Docker (`docker-compose.yml`)
- `TZ=America/Guayaquil`: Zona horaria para concordancia de logs.
- `MQTT_BROKER=${MQTT_BROKER}`: IP/Host del broker Mosquitto.

### Puertos y Volúmenes
- `1880:1880`: Editor (`/admin`) y Dashboard (`/ui`).
- `/home/rsa/data/nodered:/data`: Persistencia de flujos y estado.
- **Actualización de Flujos**: Para sincronizar cambios de `flows.json` en Git hacia el contenedor en ejecución:
  `docker cp services/node-red/flows.json rsa-nodered:/data/flows.json && docker restart rsa-nodered`

---

## 🛠️ Nodos Clave en `flows.json`

| ID del Nodo | Tipo | Propósito |
|-------------|------|-----------|
| `node-target-id` | `ui_dropdown` | Selección de estación: `broadcast`, `DEV00`, `DEV01`, `CHA01`, `CHA02`, `TENG`, `FERR`. |
| `node-timezone-select` | `ui_dropdown` | Conversión horaria entre `Tiempo Local (UTC-5)` y `Tiempo UTC`. |
| `node-build-command` | `function` | Generador dual del payload de extracción MiniSEED y de los metadatos para InfluxDB. |
| `node-mqtt-out` | `mqtt out` | Publicación de comandos y metadatos con QoS 1. |
| `node-mqtt-in` | `mqtt in` | Recepción de confirmaciones de estaciones (`cmd/extract_event/res`). |
