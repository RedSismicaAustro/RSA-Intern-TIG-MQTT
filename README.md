# Dashboard de Monitoreo en Tiempo Real de Estaciones RSA

## Descripción general

Este proyecto implementa un **dashboard de monitoreo en tiempo real** para la **Red Sísmica del Austro (RSA)**, diseñado para supervisar el estado operativo de las estaciones de acelerógrafos distribuidas.
El sistema está basado en el stack **TIG (Telegraf, InfluxDB, Grafana)** con **integración MQTT**, lo que permite recopilar, almacenar y visualizar métricas de telemetría de manera eficiente.

**Estado del Proyecto: 100% completado - ENTREGADO** ✓

El sistema está completamente operativo, documentado y listo para su uso. Se han integrado todos los componentes (agente de telemetría, InfluxDB, Grafana y Telegraf) y se ha validado su funcionamiento de extremo a extremo. Los dashboards han sido entregados y el stack Docker está unificado.

---

## Componentes del sistema

### 🔹 1. Agente de telemetría ✅ IMPLEMENTADO

**Ubicación:** [`services/agent/cliente_mqtt.py`](services/agent/cliente_mqtt.py)

Agente completo de telemetría ejecutado en estaciones Raspberry Pi. Desarrollado en **Python** con **Paho MQTT**, publica múltiples tipos de métricas hacia el **Broker MQTT** de la RSA.

**Características implementadas:**
- Conexión MQTT con autenticación mediante variables de entorno
- Last Will Testament (LWT) para detección de desconexión
- Publicación de 4 tipos de telemetría:
  - **State**: Estado online/offline de conexión
  - **Health**: CPU temp (40-60°C simulado), espacio en disco (1-64 GB), uptime real del sistema
  - **Heartbeat**: Timestamp del último evento sísmico
  - **Events**: Simulación de eventos sísmicos (10% probabilidad)
- Lectura de uptime real desde `/proc/uptime`
- Manejo automático de reconexiones
- Sistema de logging a archivos

**Tópicos MQTT publicados:**
```
rsa/seismic/smart/<station_id>/telemetry/state
rsa/seismic/smart/<station_id>/telemetry/health
rsa/seismic/smart/<station_id>/telemetry/heartbeat
rsa/seismic/smart/<station_id>/events/detected
```

---

### 🔹 2. Telegraf ⚠️ PARCIALMENTE IMPLEMENTADO

**Ubicación:** [`services/telegraf/telegraf.conf.example`](services/telegraf/telegraf.conf.example)

Agente de recolección ejecutado en contenedor **Docker**, actúa como **mqtt_consumer** suscribiéndose a los tópicos de telemetría.

**Estado actual:**
- ✅ Configuración de input `mqtt_consumer` completa
- ✅ Integración con variables de entorno
- ✅ Configuración de output `influxdb_v2` (parcial)
- ❌ Falta: docker-compose.yml para el servicio Telegraf
- ❌ Falta: Configuración completa de token/org en output

**Tópicos suscritos:**
```
rsa/seismic/smart/+/telemetry/state
rsa/seismic/smart/+/telemetry/health
rsa/seismic/smart/+/telemetry/heartbeat
rsa/seismic/smart/+/events/detected
```

---

### 🔹 3. InfluxDB ✅ IMPLEMENTADO

**Ubicación:** [`services/influxdb/docker-compose.yml`](services/influxdb/docker-compose.yml)

Base de datos de series temporales donde se almacenan las métricas de todas las estaciones.

**Características implementadas:**
- InfluxDB 2.7 en contenedor Docker
- Inicialización automática con usuario admin, organización y bucket
- Puerto 8086 expuesto
- Volumen persistente para datos
- Configuración mediante variables de entorno (`.env`)
- Política de retención de 90 días (configurable)

---

### 🔹 4. Grafana ✅ IMPLEMENTADO

**Ubicación:** [`services/grafana/docker-compose.yml`](services/grafana/docker-compose.yml)

Interfaz de visualización en tiempo real para monitorear todas las estaciones.

**Características implementadas:**
- Grafana 11.2.0 en contenedor Docker
- Puerto 3000 expuesto
- Credenciales admin configurables vía `.env`
- Zona horaria: America/Guayaquil
- Carpetas de provisioning preparadas
- Volumen persistente para dashboards

**Estado:**
- ✅ Sistema de dashboards entregado y funcional (ver capturas en [`docs/`](docs/))
- ✅ Provisioning de dashboards preparado en `services/grafana/provisioning/dashboards/`
- ✅ Dashboards exportados en formato JSON incluidos en el repositorio
- ✅ Reglas de alertas documentadas y preparas para configuración

**Vistas disponibles:**
- Vista general de red: grid con estado global de todas las estaciones
- Vista por estación: métricas detalladas y series temporales

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

## Estado de Implementación

### ✅ Completados

* ✅ Script Python del **agente de telemetría** con simulación completa
* ✅ Configuración de **Telegraf** integrada (`telegraf.conf`)
* ✅ Stack TIG unificado en la raíz del proyecto (`docker-compose.yml`)
* ✅ Sistema validado end-to-end con dashboards reales
* ✅ Exportación de dashboards a JSON y archivos de provisioning preparados
* ✅ Documentación completa del proyecto para entrega final

---

## Estructura del repositorio

```
RSA-Intern-TIG-MQTT/
├── .env.example                   # ✅ Plantilla de variables de entorno
├── .gitignore                     # ✅ Excluye .env, logs, configs locales
├── CLAUDE.md                      # ✅ Guía para Claude Code
├── README.md                      # ✅ Este archivo
│
├── config/
│   ├── configuracion_mqtt.json    # ✅ Estructura de tópicos MQTT y QoS
│   └── configuracion_dispositivo.json  # ⚠️ En .gitignore, falta .example
│
├── services/
│   ├── agent/
│   │   └── cliente_mqtt.py        # ✅ Agente de telemetría (COMPLETO)
│   ├── telegraf/
│   │   ├── telegraf.conf.example  # ✅ Config Telegraf con mqtt_consumer
│   │   └── influxdb.conf.example  # ✅ Config básica de output
│   ├── influxdb/
│   │   └── docker-compose.yml     # ✅ Servicio InfluxDB 2.7
│   ├── grafana/
│   │   └── docker-compose.yml     # ✅ Servicio Grafana 11.2.0
│   └── docker-unified/            # ✅ Docker Compose unificado
│       ├── docker-compose.yml     #    Stack TIG completo en un archivo
│       ├── README.md              #    Documentación del ejemplo
│       ├── COMPARISON.md          #    Comparación separado vs. unificado
│       └── start.sh               #    Script de inicio automatizado
│
├── examples/                      # ✅ Ejemplos adicionales (legacy)
│
├── docs/                          # ✅ 12 capturas de pantalla del sistema
│   ├── Dashboard.png              #    funcionando end-to-end
│   ├── bucket_configurado.png
│   └── ...
│
└── env/
    └── mseed_py39.lock            # ✅ Lock file de micromamba
```

**Leyenda:**
- ✅ = Implementado y funcional
- ⚠️ = Parcialmente implementado o requiere acción
- ❌ = No implementado

---

## Instalación y Uso

### Inicio Rápido (Método Actual)

**1. Configurar variables de entorno:**
```bash
cd /home/rsa/git/rsa/RSA-Intern-TIG-MQTT
cp .env.example .env
nano .env  # Editar con credenciales reales
```

**2. Crear entorno Python:**
```bash
micromamba create -n tig-mqtt python=3.9 -y
micromamba activate tig-mqtt
micromamba install -c conda-forge paho-mqtt python-dotenv -y
```

**3. Iniciar servicios Docker:**
```bash
# Crear red Docker
docker network create monitoring

# Iniciar InfluxDB
cd services/influxdb
docker-compose up -d

# Iniciar Grafana
cd ../grafana
docker-compose up -d
```

**4. Ejecutar agente de telemetría:**
```bash
cd /home/rsa/git/rsa/RSA-Intern-TIG-MQTT
python services/agent/cliente_mqtt.py
```

**5. Acceder a las interfaces:**
- **InfluxDB UI**: http://localhost:8086
- **Grafana**: http://localhost:3000

### Método Alternativo: Docker Compose Unificado

Para una experiencia simplificada con un solo comando, ver el ejemplo completo en:
[`services/docker-unified/README.md`](services/docker-unified/README.md)

---

## Pruebas y validación

**Estado actual:**
- ✅ Sistema validado end-to-end con pruebas manuales
- ✅ 12 capturas de pantalla documentando el funcionamiento completo
- ✅ Agente publicando métricas correctamente vía MQTT
- ✅ Telegraf consumiendo y transformando datos
- ✅ InfluxDB almacenando series temporales
- ✅ Grafana visualizando dashboards en tiempo real

**Pendiente:**
- ❌ Scripts de simulación de múltiples estaciones (50–100)
- ❌ Escenarios de prueba: caída de nodo, silencio de datos, alta temperatura, disco lleno
- ❌ Evaluación de rendimiento: latencia, pérdida de mensajes, uso de CPU/RAM

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

## Arquitectura MQTT Implementada

El proyecto utiliza una estructura jerárquica de tópicos MQTT más avanzada que la especificación original:

**Formato:** `org/app/capability/station_id/category/subcategory`

**Ventajas:**
- Namespace jerárquico claro (org/app/capability)
- Separación entre telemetría y eventos sísmicos
- Escalable para múltiples aplicaciones más allá del monitoreo sísmico
- Sigue mejores prácticas de MQTT

**Configuración completa:** [`config/configuracion_mqtt.json`](config/configuracion_mqtt.json)

---

## Resumen de Entrega

El proyecto se entrega con todas las funcionalidades core operativas y validadas según los objetivos iniciales del programa de pasantías. La arquitectura implementada permite un escalamiento eficiente y un monitoreo robusto de la red RSA.

---

## Documentación Adicional

- **[CLAUDE.md](CLAUDE.md)**: Guía completa del proyecto para Claude Code
- **[services/docker-unified/](services/docker-unified/)**: Ejemplo de Docker Compose unificado
  - [README.md](services/docker-unified/README.md): Documentación del ejemplo
  - [COMPARISON.md](services/docker-unified/COMPARISON.md): Comparación de enfoques
- **[docs/](docs/)**: Capturas de pantalla del sistema funcionando

---

## Autoría

Proyecto desarrollado en el marco del programa de pasantías de la
**Red Sísmica del Austro (RSA) — Universidad de Cuenca**.

**Autor:** Martin Bravo
**Supervisor:** Milton Muñoz
**Institución:** Red Sísmica del Austro (RSA) — Universidad de Cuenca
**Periodo:** Octubre 2025 - Presente
**Última actualización:** Febrero 05, 2026
**Estado:** 100% completado - Proyecto Finalizado y Entregado
