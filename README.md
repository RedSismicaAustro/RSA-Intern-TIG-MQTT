# Dashboard de Monitoreo en Tiempo Real de Estaciones RSA

## Descripción general

Este proyecto implementa un **dashboard de monitoreo en tiempo real** para la **Red Sísmica del Austro (RSA)**, diseñado para supervisar el estado operativo de las estaciones de acelerógrafos distribuidas.
El sistema está basado en el stack **TIG (Telegraf, InfluxDB, Grafana)** con **integración MQTT**, lo que permite recopilar, almacenar y visualizar métricas de telemetría de manera eficiente.

**Estado del Proyecto: ~70% completado** ✓

Los componentes principales (agente de telemetría, servicios Docker, configuración Telegraf) están implementados y probados. El sistema ha sido validado de extremo a extremo con dashboards de prueba de concepto. El trabajo restante se enfoca en el endurecimiento para producción, despliegue unificado y documentación completa.

---

## Componentes del sistema

### 🔹 1. Agente de telemetría ✅ IMPLEMENTADO

**Ubicación:** [`scripts/agent/cliente_mqtt.py`](scripts/agent/cliente_mqtt.py)

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

**Ubicación:** [`scripts/telegraf/telegraf.conf.example`](scripts/telegraf/telegraf.conf.example)

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

**Ubicación:** [`scripts/influxdb/docker-compose.yml`](scripts/influxdb/docker-compose.yml)

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

**Ubicación:** [`scripts/grafana/docker-compose.yml`](scripts/grafana/docker-compose.yml)

Interfaz de visualización en tiempo real para monitorear todas las estaciones.

**Características implementadas:**
- Grafana 11.2.0 en contenedor Docker
- Puerto 3000 expuesto
- Credenciales admin configurables vía `.env`
- Zona horaria: America/Guayaquil
- Carpetas de provisioning preparadas
- Volumen persistente para dashboards

**Estado:**
- ✅ Sistema de dashboards probado y funcional (ver capturas en [`docs/`](docs/))
- ⚠️ Falta: Provisioning automático de datasource InfluxDB
- ⚠️ Falta: Exportación de dashboards a JSON
- ❌ Falta: Reglas de alertas configuradas

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
* ✅ Configuración de **Telegraf** (`telegraf.conf.example`)
* ✅ Contenedores **InfluxDB** y **Grafana** con `docker-compose.yml` separados
* ✅ Sistema validado end-to-end (ver capturas en [`docs/`](docs/))
* ✅ Ejemplo de **Docker Compose unificado** ([`examples/docker-unified/`](examples/docker-unified/))

### ⚠️ En Progreso

* ⚠️ Docker Compose unificado en la raíz del proyecto
* ⚠️ Servicio Telegraf en Docker
* ⚠️ Provisioning automático de datasource en Grafana

### ❌ Pendientes

* ❌ Dashboards exportados en formato JSON
* ❌ Reglas de alertas Grafana configuradas
* ❌ Simulador multi-estación (50-100 estaciones)
* ❌ Manuales de instalación y operación completos
* ❌ Script de setup automatizado (`setup.sh`)

---

## Estructura del repositorio

```
RSA-Intern-TIG-MQTT/
├── .env.example                    # ✅ Plantilla de variables de entorno
├── .gitignore                      # ✅ Excluye .env, logs, configs locales
├── CLAUDE.md                       # ✅ Guía para Claude Code
├── README.md                       # ✅ Este archivo
│
├── config/
│   ├── configuracion_mqtt.json    # ✅ Estructura de tópicos MQTT y QoS
│   └── configuracion_dispositivo.json  # ⚠️ En .gitignore, falta .example
│
├── scripts/
│   ├── agent/
│   │   └── cliente_mqtt.py        # ✅ Agente de telemetría (COMPLETO)
│   ├── telegraf/
│   │   ├── telegraf.conf.example  # ✅ Config Telegraf con mqtt_consumer
│   │   └── influxdb.conf.example  # ✅ Config básica de output
│   ├── influxdb/
│   │   └── docker-compose.yml     # ✅ Servicio InfluxDB 2.7
│   └── grafana/
│       └── docker-compose.yml     # ✅ Servicio Grafana 11.2.0
│
├── examples/
│   ├── mqtt/
│   │   └── cliente_mqtt.py        # ✅ Duplicado del agente (legacy)
│   ├── docker-unified/            # ✅ Ejemplo de Docker Compose unificado
│   │   ├── docker-compose.yml     #    Stack TIG completo en un archivo
│   │   ├── README.md              #    Documentación del ejemplo
│   │   ├── COMPARISON.md          #    Comparación separado vs. unificado
│   │   └── start.sh               #    Script de inicio automatizado
│   └── grafana/
│       └── provisioning/
│           └── datasources/       # ⚠️ Vacío (falta datasource.yml)
│
├── docs/                           # ✅ 12 capturas de pantalla del sistema
│   ├── Dashboard.png              #    funcionando end-to-end
│   ├── bucket_configurado.png
│   └── ...
│
└── env/
    └── mseed_py39.lock             # ✅ Lock file de micromamba
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
cd scripts/influxdb
docker-compose up -d

# Iniciar Grafana
cd ../grafana
docker-compose up -d
```

**4. Ejecutar agente de telemetría:**
```bash
cd /home/rsa/git/rsa/RSA-Intern-TIG-MQTT
python scripts/agent/cliente_mqtt.py
```

**5. Acceder a las interfaces:**
- **InfluxDB UI**: http://localhost:8086
- **Grafana**: http://localhost:3000

### Método Alternativo: Docker Compose Unificado

Para una experiencia simplificada con un solo comando, ver el ejemplo completo en:
[`examples/docker-unified/README.md`](examples/docker-unified/README.md)

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

## Próximos Pasos

### Alta Prioridad (Requerido para Producción)

1. **Docker Compose unificado** en la raíz del proyecto
2. **Servicio Telegraf** integrado en docker-compose
3. **Provisioning automático** de datasource InfluxDB en Grafana
4. **Exportar dashboards** a JSON para persistencia
5. **Configurar reglas de alertas** en Grafana

### Prioridad Media

6. **Simulador multi-estación** para pruebas de carga
7. **Documentación completa**: manuales de instalación, operación y troubleshooting
8. **Script setup.sh** para inicialización automatizada

### Prioridad Baja

9. **Métricas adicionales**: RAM, CPU%, network throughput
10. **Tests automatizados** y CI/CD pipeline

Ver detalles completos en [`CLAUDE.md`](CLAUDE.md)

---

## Documentación Adicional

- **[CLAUDE.md](CLAUDE.md)**: Guía completa del proyecto para Claude Code
- **[examples/docker-unified/](examples/docker-unified/)**: Ejemplo de Docker Compose unificado
  - [README.md](examples/docker-unified/README.md): Documentación del ejemplo
  - [COMPARISON.md](examples/docker-unified/COMPARISON.md): Comparación de enfoques
- **[docs/](docs/)**: Capturas de pantalla del sistema funcionando

---

## Autoría

Proyecto desarrollado en el marco del programa de pasantías de la
**Red Sísmica del Austro (RSA) — Universidad de Cuenca**.

**Autor:** Martin Bravo
**Supervisor:** Milton Muñoz
**Institución:** Red Sísmica del Austro (RSA) — Universidad de Cuenca
**Periodo:** Octubre 2025 - Presente
**Última actualización:** Noviembre 18, 2025
**Estado:** 70% completado — Componentes principales funcionales, integración en progreso
