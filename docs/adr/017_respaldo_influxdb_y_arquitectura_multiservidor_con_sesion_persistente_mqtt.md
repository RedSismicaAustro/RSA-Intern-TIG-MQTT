---
id: ADR-017
titulo: Protocolo de Respaldo Híbrido de InfluxDB, Automatización Portable y Arquitectura Multi-Servidor con Sesión Persistente MQTT
estado: Aceptado
fecha: 2026-08-28
temas: [influxdb, backup, restore, rclone, gdrive, systemd, multi-servidor, mqtt, sesion-persistente, clean_session, docker-compose, profiles, arquitectura]
entorno: RSA-Intern-TIG-MQTT
---

# ADR-017: Protocolo de Respaldo Híbrido de InfluxDB, Automatización Portable y Arquitectura Multi-Servidor con Sesión Persistente MQTT

## Estado

**Aceptado** | Fecha: 2026-08-28

---

## Contexto

Con la puesta en producción del catálogo de eventos sísmicos en InfluxDB v2 (`rsa_events`), la red sísmica enfrentaba dos desafíos arquitectónicos críticos:

1. **Vulnerabilidad de Datos No Recuperables**: A diferencia del bucket `telemetry` (retención de 90 días, regenerable desde el tráfico continuo de las estaciones), el bucket `rsa_events` contiene metadatos consolidados de clasificaciones manuales y automáticas con retención infinita. Una falla de hardware, corrupción de base de datos o borrado accidental ocasionaría la pérdida irreversible del catálogo histórico.
2. **Riesgo de Pérdida de Alertas ante Cortes de Energía (Escenario R4)**: En la arquitectura multi-servidor (`rsa-server` primario en oficina vs `home-server` espejo pasivo en contingencia), los cortes prolongados de energía en la oficina desconectan el correlador regional. Sin mecanismos de retención en el broker MQTT, las alertas de eventos emitidas por las estaciones con respaldo de batería se perderían en el vacío.
3. **Riesgo de Duplicación de Procesamiento y Colisiones**: Desplegar el stack en múltiples servidores con el correlador activo generaría órdenes broadcast duplicadas a las estaciones acelerográficas y condiciones de carrera en la asignación de IDs de eventos.
4. **Rigidez en la Automatización Operativa**: Unidades de automatización con rutas o usuarios fijos (*hardcodeados*) impedían la portabilidad del sistema entre servidores con diferentes estructuras de carpetas o usuarios de sistema.

---

## Opciones Evaluadas

### Opción A: Replicación Activo-Activo y Motor de Sincronización Bidireccional
- **Descripción**: Ejecutar el correlador en ambos servidores con algoritmos de consenso distribuido y sincronización de base de datos entre InfluxDB primario y secundario.
- **Ventajas**: Tolerancia total sin intervención.
- **Desventajas**: 
  - Complejidad innecesaria para la escala de la red.
  - Sobrecarga de red y riesgo de split-brain ante desconexiones parciales.
  - Mayor costo de mantenimiento.

### Opción B: Respaldo Híbrido (Snapshot + CSV), Perfiles Compose (`primary`/`mirror`) y Sesión Persistente MQTT (Seleccionada)
- **Descripción**:
  1. **Estrategia de Respaldo Híbrido**: Snapshot binario nativo (`influx backup`) para recuperación destructiva exacta + exportación tabular plana (`Flux pivot`) a CSV para interoperabilidad y auditoría, con subida a Google Drive (`rclone`) y rotación estricta de 7 días.
  2. **Automatización Portable Systemd**: Gestor unificado con plantillas parametrizadas (`.template`) que detecta dinámicamente el usuario (`SUDO_USER`), grupo y rutas absolutas.
  3. **Sesión Persistente MQTT en Correlador**: Uso de `client_id` estático (`RSA_CORRELATOR_CLIENT_ID`) y `clean_session=False` con suscripciones QoS 1, delegando al broker Mosquitto la retención y encolado de alertas ante caídas del servidor.
  4. **Aislamiento por Perfiles Docker Compose**: Servicio `correlator` bajo `profiles: ["primary"]`, corriendo exclusivamente en `rsa-server` mientras `home-server` opera en modo espejo pasivo (ingesta, visualización y clasificación).
- **Ventajas**:
  - Cero pérdida de alertas sísmicas durante cortes eléctricos.
  - Prevención garantizada de órdenes broadcast duplicadas.
  - Recuperación ante desastres en menos de 2 minutos vía `restore_events.sh`.
  - Portabilidad total del repositorio en cualquier máquina Linux sin modificar código.
- **Desventajas**:
  - El servidor espejo requiere una restauración bajo demanda (`restore_events.sh --latest`) para sincronizar el historial previo al momento de su despliegue inicial.

---

## Decisión

Se eligió la **Opción B**:

1. **Protocolo de Respaldo y Restauración**:
   - Se implementaron [`scripts/db_sync/backup_events.sh`](file:///home/rsa/git/montajes/server-ubuntu/rsa/RSA-Intern-TIG-MQTT/scripts/db_sync/backup_events.sh) y [`scripts/db_sync/restore_events.sh`](file:///home/rsa/git/montajes/server-ubuntu/rsa/RSA-Intern-TIG-MQTT/scripts/db_sync/restore_events.sh).
   - Se creó el microservicio contenedorizado [`scripts/db_sync/Dockerfile`](file:///home/rsa/git/montajes/server-ubuntu/rsa/RSA-Intern-TIG-MQTT/scripts/db_sync/Dockerfile) y [`scripts/db_sync/mqtt_notify.py`](file:///home/rsa/git/montajes/server-ubuntu/rsa/RSA-Intern-TIG-MQTT/scripts/db_sync/mqtt_notify.py) para emitir telemetría de respaldo al tópico `rsa/seismic/smart/system/backup` con QoS 1.
2. **Automatización Portable**:
   - Se crearon [`services/systemd/manage_backup_timer.sh`](file:///home/rsa/git/montajes/server-ubuntu/rsa/RSA-Intern-TIG-MQTT/services/systemd/manage_backup_timer.sh), [`services/systemd/rsa-backup-events.service.template`](file:///home/rsa/git/montajes/server-ubuntu/rsa/RSA-Intern-TIG-MQTT/services/systemd/rsa-backup-events.service.template) y [`services/systemd/rsa-backup-events.timer.template`](file:///home/rsa/git/montajes/server-ubuntu/rsa/RSA-Intern-TIG-MQTT/services/systemd/rsa-backup-events.timer.template).
   - El temporizador ejecuta diariamente a las 02:00 UTC con persistencia ante reinicios (`Persistent=true`).
3. **Resiliencia MQTT y Arquitectura Multi-Servidor**:
   - En [`scripts/correlator/regional_event_correlator.py`](file:///home/rsa/git/montajes/server-ubuntu/rsa/RSA-Intern-TIG-MQTT/scripts/correlator/regional_event_correlator.py) se configuró `client_id = os.getenv("RSA_CORRELATOR_CLIENT_ID", ...)` y `clean_session=False`.
   - En [`services/docker-unified/docker-compose.yml`](file:///home/rsa/git/montajes/server-ubuntu/rsa/RSA-Intern-TIG-MQTT/services/docker-unified/docker-compose.yml) se asignó `profiles: ["primary"]` al correlador.
   - En [`services/docker-unified/.env.example`](file:///home/rsa/git/montajes/server-ubuntu/rsa/RSA-Intern-TIG-MQTT/services/docker-unified/.env.example) se documentaron las variables `RSA_SERVER_ROLE` y `RSA_CORRELATOR_CLIENT_ID`.

---

## Consecuencias

### Positivas
- **Inmunidad ante Apagones**: Las alertas emitidas por las estaciones durante caídas del servidor primario son retenidas por Mosquitto y procesadas en ráfaga tan pronto el correlador vuelve a estar en línea.
- **Trazabilidad y Respaldo Doble**: Disponibilidad simultánea del snapshot binario TSM y del catálogo en formato CSV para análisis en herramientas sismológicas externas o Python.
- **Despliegue Portable**: El repositorio puede clonarse y desplegarse en cualquier host sin requerir ajustes manuales de rutas o nombres de usuario en systemd.
- **Control Centralizado**: Un único nodo procesa la lógica regional evitando órdenes broadcast redundantes a las estaciones.

### Negativas / Deuda Técnica Mitigada
- **Caducidad en el Broker**: Los mensajes encolados en Mosquitto dependen de la política de expiración configurada en el broker (`persistent_client_expiration 7d`).
- **Limpieza Manual en Servidor Espejo**: Si `home-server` se mantiene apagado por semanas, requiere ejecutar `restore_events.sh --latest` para ponerse al día con el historial previo.

---

## Referencias

- Plan Maestro de Implementación: [`docs/blueprints/2026-08-26_fase5_implementation_plan.md`](file:///home/rsa/git/montajes/server-ubuntu/rsa/RSA-Intern-TIG-MQTT/docs/blueprints/2026-08-26_fase5_implementation_plan.md)
- Contexto Técnico de Backup: [`docs/context/backup_events_context.md`](file:///home/rsa/git/montajes/server-ubuntu/rsa/RSA-Intern-TIG-MQTT/docs/context/backup_events_context.md)
- Contexto Técnico de Systemd: [`docs/context/manage_backup_timer_context.md`](file:///home/rsa/git/montajes/server-ubuntu/rsa/RSA-Intern-TIG-MQTT/docs/context/manage_backup_timer_context.md)
- Contexto Técnico del Correlador: [`docs/context/regional_event_correlator_context.md`](file:///home/rsa/git/montajes/server-ubuntu/rsa/RSA-Intern-TIG-MQTT/docs/context/regional_event_correlator_context.md)
