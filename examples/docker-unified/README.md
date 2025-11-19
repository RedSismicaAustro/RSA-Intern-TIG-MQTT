# Ejemplo: Docker Compose Unificado - TIG Stack

Este directorio contiene un **ejemplo completo** de cómo usar Docker Compose para orquestar el stack TIG (Telegraf, InfluxDB, Grafana) en un único archivo.

## Ventajas vs. Docker Compose Separados

| Aspecto | Docker Compose Separado | Docker Compose Unificado |
|---------|------------------------|--------------------------|
| Archivos | 2-3 archivos en diferentes carpetas | 1 archivo en la raíz |
| Inicio | `cd scripts/influxdb && docker-compose up -d`<br>`cd scripts/grafana && docker-compose up -d` | `docker-compose up -d` |
| Red Docker | Crear manualmente: `docker network create monitoring` | Creada automáticamente |
| Orden de inicio | Manual (esperar entre comandos) | Automático con `depends_on` |
| Ver logs | `docker logs influxdb`<br>`docker logs grafana` | `docker-compose logs -f` |
| Detener todo | Detener contenedores uno por uno | `docker-compose down` |

## Estructura del Stack

```
┌─────────────────┐
│  Telemetry Agent│  (Python - scripts/agent/cliente_mqtt.py)
│   (Raspberry Pi)│
└────────┬────────┘
         │ MQTT
         ↓
┌─────────────────┐
│  MQTT Broker    │  (Mosquitto - externo al stack)
│  (RSA Network)  │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│    Telegraf     │  mqtt_consumer → influxdb_v2 output
│  (Container 1)  │  - Consume mensajes MQTT
└────────┬────────┘  - Parsea y transforma datos
         │           - Envía a InfluxDB
         ↓
┌─────────────────┐
│    InfluxDB     │  Base de datos de series temporales
│  (Container 2)  │  - Puerto: 8086
└────────┬────────┘  - Retención: 90 días
         │
         ↓
┌─────────────────┐
│    Grafana      │  Dashboard de visualización
│  (Container 3)  │  - Puerto: 3000
└─────────────────┘  - Usuario: admin
```

## Configuración

### 1. Variables de Entorno

Copia el archivo de ejemplo y edítalo con tus credenciales:

```bash
cd examples/docker-unified
cp .env.example .env
nano .env  # o vim, code, etc.
```

Configura las siguientes variables clave:

```bash
# MQTT Broker (ajustar a tu entorno)
MQTT_BROKER=192.168.1.100  # IP del broker Mosquitto
MQTT_USERNAME=rsa_user
MQTT_PASSWORD=secure_password

# InfluxDB (genera un token seguro)
INFLUXDB_TOKEN=$(openssl rand -hex 32)  # O pon uno manualmente

# Grafana
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=secure_password
```

### 2. Configuración de Telegraf

El archivo `docker-compose.yml` monta la configuración desde:
```
../../scripts/telegraf/telegraf.conf
```

**Importante**: Asegúrate de que este archivo existe y está configurado correctamente. Debe incluir:

**Input (MQTT Consumer)**:
```toml
[[inputs.mqtt_consumer]]
  servers = ["tcp://${MQTT_BROKER}:1883"]
  topics = [
    "rsa/seismic/smart/+/telemetry/state",
    "rsa/seismic/smart/+/telemetry/health",
    "rsa/seismic/smart/+/telemetry/heartbeat",
    "rsa/seismic/smart/+/events/detected"
  ]
  username = "${MQTT_USERNAME}"
  password = "${MQTT_PASSWORD}"
  data_format = "json"
```

**Output (InfluxDB v2)**:
```toml
[[outputs.influxdb_v2]]
  urls = ["${INFLUXDB_URL}"]
  token = "${INFLUXDB_TOKEN}"
  organization = "${INFLUXDB_ORG}"
  bucket = "${INFLUXDB_BUCKET}"
```

## Uso

### Iniciar el Stack Completo

```bash
cd examples/docker-unified
docker-compose up -d
```

**Salida esperada**:
```
Creating network "docker-unified_monitoring" ... done
Creating rsa-influxdb ... done
Creating rsa-telegraf ... done
Creating rsa-grafana  ... done
```

### Verificar Estado de los Servicios

```bash
docker-compose ps
```

**Salida esperada**:
```
NAME             STATUS         PORTS
rsa-influxdb     Up (healthy)   0.0.0.0:8086->8086/tcp
rsa-telegraf     Up
rsa-grafana      Up (healthy)   0.0.0.0:3000->3000/tcp
```

### Ver Logs en Tiempo Real

**Todos los servicios**:
```bash
docker-compose logs -f
```

**Servicio específico**:
```bash
docker-compose logs -f telegraf
docker-compose logs -f influxdb
docker-compose logs -f grafana
```

### Acceder a las Interfaces Web

- **InfluxDB UI**: http://localhost:8086
  - Usuario: valor de `INFLUXDB_ADMIN_USER` en `.env`
  - Contraseña: valor de `INFLUXDB_ADMIN_PASSWORD` en `.env`

- **Grafana**: http://localhost:3000
  - Usuario: valor de `GRAFANA_ADMIN_USER` en `.env`
  - Contraseña: valor de `GRAFANA_ADMIN_PASSWORD` en `.env`

### Reiniciar un Servicio Específico

```bash
# Reiniciar Telegraf (útil después de cambiar telegraf.conf)
docker-compose restart telegraf

# Reiniciar todos los servicios
docker-compose restart
```

### Detener el Stack

```bash
# Detener sin eliminar datos
docker-compose stop

# Detener y eliminar contenedores (pero mantener datos en volúmenes)
docker-compose down

# Detener y eliminar TODO (incluyendo datos)
docker-compose down -v  # ⚠️ CUIDADO: Elimina todos los datos
```

## Verificación del Flujo de Datos

### 1. Ejecutar el Agente de Telemetría

```bash
# En otra terminal
cd ../../  # Volver a la raíz del proyecto
python scripts/agent/cliente_mqtt.py
```

### 2. Verificar que Telegraf Recibe Datos

```bash
docker-compose logs -f telegraf
```

Deberías ver mensajes como:
```
2025-11-18T10:30:00Z I! [inputs.mqtt_consumer] Connected to broker
2025-11-18T10:30:01Z D! [inputs.mqtt_consumer] Received message on topic: rsa/seismic/smart/NOM00/telemetry/state
```

### 3. Verificar Datos en InfluxDB

Accede a http://localhost:8086 → Data Explorer

Ejecuta una query:
```flux
from(bucket: "telemetry")
  |> range(start: -1h)
  |> filter(fn: (r) => r["_measurement"] == "mqtt_consumer")
```

### 4. Crear Dashboard en Grafana

1. Accede a http://localhost:3000
2. Añadir datasource: Configuration → Data Sources → Add data source → InfluxDB
   - Query Language: Flux
   - URL: `http://influxdb:8086`
   - Organization: valor de `INFLUXDB_ORG`
   - Token: valor de `INFLUXDB_TOKEN`
   - Default bucket: valor de `INFLUXDB_BUCKET`
3. Crear dashboard con paneles para: temperatura CPU, disco libre, uptime, etc.

## Troubleshooting

### Error: "network monitoring declared as external, but could not be found"

Si los servicios no pueden comunicarse, verifica que la red existe:

```bash
docker network ls | grep monitoring
```

Si no existe, el docker-compose debería crearla automáticamente. Si persiste el error, créala manualmente:

```bash
docker network create docker-unified_monitoring
```

### Error: Telegraf no puede conectarse a InfluxDB

Verifica que InfluxDB esté saludable antes de que Telegraf inicie:

```bash
docker-compose ps
```

InfluxDB debe mostrar `(healthy)`. Si no:

```bash
docker-compose logs influxdb
```

### Error: "connection refused" al acceder a Grafana

Verifica que Grafana esté corriendo:

```bash
docker-compose ps grafana
docker-compose logs grafana
```

Espera hasta que veas:
```
HTTP Server Listen [::]:3000
```

### No hay datos en InfluxDB

1. Verifica que el agente MQTT está publicando:
   ```bash
   mosquitto_sub -h <MQTT_BROKER> -u <USERNAME> -P <PASSWORD> -t "rsa/seismic/smart/#" -v
   ```

2. Verifica que Telegraf recibe datos:
   ```bash
   docker-compose logs telegraf | grep "mqtt_consumer"
   ```

3. Verifica configuración de Telegraf:
   ```bash
   docker-compose exec telegraf cat /etc/telegraf/telegraf.conf | grep -A 20 mqtt_consumer
   ```

## Diferencias con la Implementación Actual

Este ejemplo es **standalone** y no modifica tu configuración actual. Las diferencias son:

| Aspecto | Implementación Actual | Este Ejemplo |
|---------|----------------------|--------------|
| Ubicación | `scripts/influxdb/` y `scripts/grafana/` | `examples/docker-unified/` |
| Red | `monitoring` (externa) | `docker-unified_monitoring` (interna) |
| Telegraf | No incluido en docker-compose | Incluido en el stack |
| Variables | `.env` en raíz | `.env` en este directorio |

## Próximos Pasos

Para usar este ejemplo en producción:

1. **Copiar** `docker-compose.yml` a la raíz del proyecto
2. **Renombrar** red de `docker-unified_monitoring` a `monitoring`
3. **Ajustar** rutas de volúmenes si es necesario
4. **Mover** `.env.example` a la raíz
5. **Actualizar** documentación del proyecto

## Referencias

- [Docker Compose Docs](https://docs.docker.com/compose/)
- [InfluxDB v2 Docs](https://docs.influxdata.com/influxdb/v2/)
- [Telegraf MQTT Consumer](https://github.com/influxdata/telegraf/tree/master/plugins/inputs/mqtt_consumer)
- [Grafana Provisioning](https://grafana.com/docs/grafana/latest/administration/provisioning/)
