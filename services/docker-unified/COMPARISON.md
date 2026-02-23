# Comparación: Docker Compose Separado vs. Unificado

Este documento compara las dos aproximaciones para desplegar el stack TIG en tu proyecto.

## Visualización de Arquitecturas

### Enfoque Actual (Separado)

```
Proyecto RSA-Intern-TIG-MQTT/
│
├── services/
│   ├── influxdb/
│   │   └── docker-compose.yml ──┐
│   │       services:            │  Red externa "monitoring"
│   │         influxdb           │  (crear manualmente)
│   │       networks:            │
│   │         monitoring:        │
│   │           external: true ──┤
│   │                            │
│   └── grafana/                 │
│       └── docker-compose.yml ──┤
│           services:            │
│             grafana            │
│           networks:            │
│             monitoring:        │
│               external: true ──┘
│
└── Telegraf: ❌ NO incluido
```

**Comandos necesarios:**
```bash
# Paso 1: Crear red manualmente
docker network create monitoring

# Paso 2: Iniciar InfluxDB
cd services/influxdb
docker-compose up -d

# Paso 3: Iniciar Grafana
cd ../grafana
docker-compose up -d

# Paso 4: Configurar Telegraf manualmente
# (no hay docker-compose, requiere docker run manual)
```

### Enfoque Unificado (Este Ejemplo)

```
Proyecto RSA-Intern-TIG-MQTT/
│
└── docker-compose.yml (raíz o en examples/)
    services:
      ┌────────────────┐
      │   influxdb     │◄─── healthcheck
      └────────┬───────┘
               │
      ┌────────▼───────┐
      │   telegraf     │  depends_on: influxdb (healthy)
      └────────┬───────┘
               │
      ┌────────▼───────┐
      │    grafana     │  depends_on: influxdb
      └────────────────┘
    networks:
      monitoring:
        driver: bridge  ◄─── Creada automáticamente
```

**Comando único:**
```bash
docker-compose up -d
```

## Tabla Comparativa Detallada

| Característica | Separado (Actual) | Unificado (Ejemplo) | Ganador |
|----------------|-------------------|---------------------|---------|
| **Configuración Inicial** |
| Archivos docker-compose | 2 archivos | 1 archivo | 🏆 Unificado |
| Configuración de red | Manual (`docker network create`) | Automática | 🏆 Unificado |
| Variables de entorno | Duplicadas en cada archivo | Centralizadas en 1 `.env` | 🏆 Unificado |
| **Operación Diaria** |
| Iniciar todos los servicios | 2-3 comandos | 1 comando | 🏆 Unificado |
| Detener todos los servicios | 2-3 comandos | 1 comando | 🏆 Unificado |
| Ver logs de todos | `docker logs <cada-uno>` | `docker-compose logs -f` | 🏆 Unificado |
| Reiniciar un servicio | `docker restart <nombre>` | `docker-compose restart <servicio>` | ≈ Empate |
| **Gestión de Dependencias** |
| Orden de inicio | Manual (esperar entre comandos) | Automático con `depends_on` | 🏆 Unificado |
| Health checks | No coordinados | Telegraf espera a InfluxDB healthy | 🏆 Unificado |
| **Comunicación Entre Servicios** |
| Descubrimiento de red | Por nombre (misma red externa) | Por nombre (red interna) | ≈ Empate |
| URLs de conexión | `http://<container-name>:port` | `http://<service-name>:port` | ≈ Empate |
| **Portabilidad** |
| Replicar en otro servidor | Copiar 2+ archivos + crear red | Copiar 1 archivo + 1 `.env` | 🏆 Unificado |
| Compartir con equipo | Múltiples pasos en docs | Clonar repo + `docker-compose up` | 🏆 Unificado |
| **Organización del Código** |
| Estructura de carpetas | Servicios separados por función | Todo en un lugar | 🤔 Depende |
| Facilidad de encontrar config | Cada config en su carpeta | Todo en 1 archivo (puede ser largo) | 🤔 Depende |
| **Debugging** |
| Ver estado de servicios | `docker ps` (ver todos contenedores) | `docker-compose ps` (solo stack) | 🏆 Unificado |
| Ver logs con filtros | Requiere múltiples comandos | `docker-compose logs -f <servicio>` | 🏆 Unificado |
| **Escalabilidad** |
| Añadir nuevo servicio | Crear nuevo docker-compose | Añadir al archivo existente | ≈ Empate |
| Escalar horizontalmente | `docker run` múltiples | `docker-compose up --scale` | 🏆 Unificado |
| **Telegraf** |
| Incluido en docker-compose | ❌ No | ✅ Sí | 🏆 Unificado |
| Configuración | Manual con `docker run` | Automática con depends_on | 🏆 Unificado |

## Flujos de Trabajo Comparados

### Caso 1: Primer Despliegue del Sistema

**Separado:**
```bash
# Terminal 1
cd RSA-Intern-TIG-MQTT
docker network create monitoring

# Terminal 2
cd services/influxdb
docker-compose up -d
# Esperar 30 segundos para que InfluxDB esté listo

# Terminal 3
cd services/grafana
docker-compose up -d

# Terminal 4 - Telegraf (configuración manual)
docker run -d \
  --name telegraf \
  --network monitoring \
  -v $(pwd)/services/telegraf/telegraf.conf:/etc/telegraf/telegraf.conf:ro \
  -e MQTT_BROKER=$MQTT_BROKER \
  -e MQTT_USERNAME=$MQTT_USERNAME \
  -e MQTT_PASSWORD=$MQTT_PASSWORD \
  -e INFLUXDB_URL=http://influxdb:8086 \
  -e INFLUXDB_TOKEN=$INFLUXDB_TOKEN \
  telegraf:1.28

# Verificar cada servicio por separado
docker logs influxdb
docker logs grafana
docker logs telegraf
```

**Unificado:**
```bash
cd RSA-Intern-TIG-MQTT/services/docker-unified
cp .env.example .env
nano .env  # Configurar credenciales

# Opción 1: Manual
docker-compose up -d

# Opción 2: Script automatizado
./start.sh

# Ver estado de todo
docker-compose ps
docker-compose logs -f
```

**Tiempo estimado:**
- Separado: 10-15 minutos (con errores de orden)
- Unificado: 2-3 minutos

---

### Caso 2: Reiniciar Telegraf Después de Cambiar Configuración

**Separado:**
```bash
# Editar configuración
nano services/telegraf/telegraf.conf

# Encontrar nombre del contenedor
docker ps | grep telegraf

# Reiniciar contenedor
docker restart telegraf

# Ver si hay errores
docker logs -f telegraf
```

**Unificado:**
```bash
# Editar configuración
nano services/telegraf/telegraf.conf

# Reiniciar desde docker-compose
cd services/docker-unified
docker-compose restart telegraf

# Ver logs
docker-compose logs -f telegraf
```

**Tiempo estimado:**
- Separado: 1-2 minutos
- Unificado: 30 segundos

---

### Caso 3: Debugging - Telegraf No Recibe Datos MQTT

**Separado:**
```bash
# Ver logs de Telegraf
docker logs -f telegraf

# ¿Está Telegraf en la red correcta?
docker inspect telegraf | grep NetworkMode

# ¿Puede Telegraf alcanzar InfluxDB?
docker exec telegraf ping influxdb

# ¿Las variables de entorno están configuradas?
docker exec telegraf env | grep MQTT
docker exec telegraf env | grep INFLUXDB

# Ver configuración montada
docker exec telegraf cat /etc/telegraf/telegraf.conf | grep mqtt_consumer -A 20
```

**Unificado:**
```bash
# Ver logs con contexto
docker-compose logs telegraf influxdb

# Ejecutar comandos de debug
docker-compose exec telegraf ping influxdb
docker-compose exec telegraf env | grep MQTT

# Verificar configuración
docker-compose exec telegraf cat /etc/telegraf/telegraf.conf | grep mqtt_consumer -A 20

# Reiniciar con logs en vivo
docker-compose restart telegraf && docker-compose logs -f telegraf
```

**Tiempo estimado:**
- Separado: 5-10 minutos (buscando nombres de contenedores)
- Unificado: 2-3 minutos (nombres conocidos)

---

### Caso 4: Actualizar a Nueva Versión de Grafana

**Separado:**
```bash
cd services/grafana
nano docker-compose.yml  # Cambiar versión de imagen

docker-compose down
docker-compose up -d

# InfluxDB y Telegraf NO se ven afectados (ventaja)
```

**Unificado:**
```bash
cd services/docker-unified
nano docker-compose.yml  # Cambiar versión de imagen

docker-compose up -d grafana  # Solo actualizar Grafana

# O forzar recreación
docker-compose up -d --force-recreate grafana
```

**Tiempo estimado:**
- Separado: 2 minutos
- Unificado: 2 minutos (empate)

---

### Caso 5: Limpiar Todo y Empezar de Cero

**Separado:**
```bash
cd services/influxdb
docker-compose down -v

cd ../grafana
docker-compose down -v

docker stop telegraf
docker rm telegraf

docker network rm monitoring

# Eliminar volúmenes huérfanos
docker volume prune
```

**Unificado:**
```bash
cd services/docker-unified
docker-compose down -v

# Opcionalmente eliminar volúmenes nombrados
docker volume rm docker-unified_influxdb_data
docker volume rm docker-unified_grafana_data
```

**Tiempo estimado:**
- Separado: 3-4 minutos
- Unificado: 30 segundos

---

## Ventajas del Enfoque Separado

Aunque el enfoque unificado tiene más ventajas, el separado tiene algunos casos de uso válidos:

1. **Actualizaciones independientes**: Puedes actualizar InfluxDB sin tocar Grafana
2. **Desarrollo modular**: Equipos diferentes pueden trabajar en servicios diferentes
3. **Despliegue parcial**: Puedes desplegar solo Grafana en un servidor y solo InfluxDB en otro
4. **Menor acoplamiento**: Cambios en un servicio no requieren editar el docker-compose de otros

## Recomendación Final

### Usa Docker Compose Unificado si:
- ✅ Estás en desarrollo local
- ✅ Quieres despliegue rápido y simple
- ✅ Todos los servicios van en el mismo servidor
- ✅ Priorizas facilidad de uso sobre modularidad
- ✅ Trabajas solo o en equipo pequeño

### Usa Docker Compose Separado si:
- ✅ Despliegas servicios en servidores diferentes
- ✅ Diferentes equipos gestionan diferentes servicios
- ✅ Necesitas actualizar servicios de forma muy independiente
- ✅ Tienes infraestructura compleja con múltiples stacks

## Migración del Proyecto Actual

Para migrar tu proyecto de separado a unificado:

```bash
# 1. Copiar docker-compose.yml unificado a la raíz
cp services/docker-unified/docker-compose.yml .

# 2. Actualizar rutas de volúmenes (ya no son relativos desde services/)
nano docker-compose.yml
# Cambiar: ../../services/telegraf/telegraf.conf
# Por:     ./services/telegraf/telegraf.conf

# 3. Detener servicios actuales
cd services/influxdb && docker-compose down
cd ../grafana && docker-compose down
docker stop telegraf 2>/dev/null || true

# 4. Iniciar stack unificado
cd ../..  # Volver a raíz
docker-compose up -d

# 5. (Opcional) Eliminar docker-compose antiguos
# rm services/influxdb/docker-compose.yml
# rm services/grafana/docker-compose.yml
```

**Nota**: Mantén backups de tus configuraciones antes de migrar.
