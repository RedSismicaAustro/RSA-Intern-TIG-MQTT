# Dashboard de Monitoreo en Tiempo Real de Estaciones RSA

## Descripción general

Este proyecto implementa un **dashboard de monitoreo en tiempo real** para la **Red Sísmica del Austro (RSA)**, diseñado para supervisar el estado operativo de las estaciones de acelerógrafos distribuidas.
El sistema está basado en el stack **TIG (Telegraf, InfluxDB, Grafana)** con **integración MQTT**, lo que permite recopilar, almacenar y visualizar métricas de telemetría de manera eficiente.

El objetivo es proporcionar visibilidad centralizada de los equipos remotos, detectar fallos tempranos y mantener un historial de métricas para análisis posterior.

---

## Componentes del sistema

### 🔹 1. Agente de telemetría

Simula la operación de un agente ejecutado en las estaciones Raspberry Pi.
Desarrollado en **Python** con la librería **Paho MQTT**, publica métricas cada *N* segundos hacia un **Broker MQTT** proporcionado por la RSA.
En esta fase, se utiliza un **script simulador** que emite las métricas siguientes:

* `online`: Estado de conexión (True/False)
* `temp_cpu`: Temperatura del CPU (°C)
* `disk_free_gb`: Espacio libre en disco
* `uptime_s`: Tiempo desde el último arranque
* `last_event_ts`: Marca temporal del último evento registrado

Incluye configuración **LWT (Last Will Testament)** para marcar el estado *offline* en caso de pérdida de conexión.

---

### 🔹 2. Telegraf

Ejecutado dentro de un contenedor **Docker**, actúa como **mqtt_consumer**, suscribiéndose a los tópicos definidos por la convención:

```
rsa/telemetry/<station>/state|env|disk|frames|meta
```

Convierte los mensajes JSON recibidos en registros y los reenvía a **InfluxDB** para su almacenamiento.

---

### 🔹 3. InfluxDB

Base de datos de series temporales donde se almacenan las métricas de todas las estaciones.
Se aplica una **política de retención de 90 días** para garantizar un historial suficiente sin saturar el almacenamiento.

---

### 🔹 4. Grafana

Interfaz de visualización en tiempo real para:

* Monitorear el estado *online/offline* de cada estación
* Consultar temperatura, espacio libre, tiempo de actividad y último evento
* Recibir **alertas** configurables ante condiciones críticas

Las vistas principales son:

* **Vista general de red:** grid con el estado global de todas las estaciones.
* **Vista por estación:** panel con métricas detalladas y series temporales.

---

## Flujo de datos

```
Agente de Telemetría (Python)
        ↓ MQTT
Broker Mosquitto (RSA)
        ↓
Telegraf (mqtt_consumer)
        ↓
InfluxDB (time-series storage)
        ↓
Grafana (visualización y alertas)
```

---

## Esquema de alertas

El sistema genera notificaciones cuando:

* **Caída de estación:** LWT recibido o sin datos > X s
* **Silencio prolongado:** `last_event_ts` excede umbral
* **Temperatura alta:** `temp_cpu` > 60 °C
* **Espacio en disco bajo:** `disk_free_gb` < 1 GB

---

## Entregables principales

* Script Python del **agente de telemetría simulado**
* Configuración de **Telegraf** (`telegraf.conf`)
* Contenedores **InfluxDB** y **Grafana** con `docker-compose.yml`
* Dashboards exportados en formato JSON
* Reglas de alertas Grafana (`alerts.yaml` o JSON)
* Manuales de instalación y operación

---

## Estructura del repositorio

```
RSA-Intern-TIG-MQTT/
│
├── config/                 # Archivos de configuración JSON
│   ├── configuracion_mqtt.json
│   └── configuracion_dispositivo.json
├── scripts/
│   ├── agent/             # Script de telemetría simulado (Python)
│   ├── telegraf/          # Archivos de configuración Telegraf
│   ├── influxdb/          # Configuración y políticas de retención
│   └── grafana/           # Dashboards y configuración de alertas
├── examples/
│   └── mqtt/              # Ejemplos de cliente MQTT
├── docs/                  # Documentación del proyecto
├── env/                   # Variables de entorno
├── docker-compose.yml     # (pendiente)
├── .env.example           # (pendiente)
└── README.md
```

---

## Pruebas y validación

Se incluyen scripts de simulación de múltiples estaciones (50–100) con diferentes escenarios:

* Caída de nodo
* Silencio de datos
* Alta temperatura
* Poco espacio en disco

El rendimiento se evalúa midiendo latencia, pérdida de mensajes y uso de CPU/RAM.

---

## Beneficios esperados

* Monitoreo unificado y en tiempo real del estado de la red RSA.
* Reducción del tiempo de respuesta ante fallos.
* Conservación de métricas históricas para análisis de rendimiento.
* Base para futuras integraciones con sistemas de alerta avanzada o detección de eventos sísmicos.

---

## Recursos proporcionados

* Acceso al **Broker MQTT** de la RSA.
* Acceso a este repositorio con ejemplos, Dockerfiles y documentación.
* Instructivos de instalación y configuración del entorno en Ubuntu/WSL.

---

## Autoría

Proyecto desarrollado en el marco del programa de pasantías de la
**Red Sísmica del Austro (RSA) — Universidad de Cuenca**.
**Autor:** *Martin Bravo*
**Supervisor:** *Milton Muñoz*
**Periodo:** Octubre 2025
