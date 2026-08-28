# Resumen de Sesión: Implementación, Despliegue y Validación Integral de la Fase 5 (Respaldo, Recuperación, Automatización Systemd y Arquitectura Multi-Servidor)

**Fecha**: 2026-08-28  
**Repositorio**: `RSA-Intern-TIG-MQTT`  
**Agente de IA**: Antigravity  
**Usuario**: Milton  

---

## 🎯 Objetivo de la Sesión

Implementar, desplegar y validar en el servidor primario de producción (`rsa-server`) la totalidad de la **Fase 5** del proyecto `RSA-Intern-TIG-MQTT`:
1. **Subfase 5A.1**: Creación del contenedor utilitario portable `rsa-db-sync` para ejecución de scripts y notificaciones sin dependencias en el host.
2. **Subfase 5A.2**: Desarrollo de los scripts core `backup_events.sh` (snapshot binario + exportación CSV + subida a Google Drive + rotación de 7 días) y `restore_events.sh` (recuperación destructiva interactiva).
3. **Subfase 5A.3**: Automatización portable con `systemd` mediante el gestor unificado `manage_backup_timer.sh` y plantillas parametrizadas (`.template`), eliminando rutas y usuarios hardcodeados.
4. **Subfase 5B**: Configuración multi-servidor con perfiles de Docker Compose (`profiles: ["primary"]`), sesión persistente MQTT (`clean_session=False` con `client_id` estático) y validación de retención de alertas ante caídas/cortes de energía.
5. **Cierre y Documentación**: Actualización exhaustiva del `README.md`, generación de contextos técnicos (`docs/context/`) y extracción del `ADR-017`.

---

## 📂 Estructura del Repositorio Implementada

```text
RSA-Intern-TIG-MQTT/
├── README.md                                          # [ACTUALIZADO] Arquitectura, roles y guía universal de despliegue
├── docs/
│   ├── adr/
│   │   ├── 016_resolucion_global_trazas_y_determinacion_temporal_event_id.md
│   │   └── 017_respaldo_influxdb_y_arquitectura_multiservidor_con_sesion_persistente_mqtt.md # [NUEVO] ADR Fase 5
│   ├── blueprints/
│   │   └── 2026-08-26_fase5_implementation_plan.md   # Plan maestro ejecutado
│   ├── context/
│   │   ├── backup_events_context.md                   # [NUEVO] Contexto script de respaldo
│   │   ├── restore_events_context.md                  # [NUEVO] Contexto script de restauración
│   │   ├── mqtt_notify_context.md                     # [NUEVO] Contexto notificador MQTT
│   │   ├── manage_backup_timer_context.md             # [NUEVO] Contexto gestor systemd
│   │   ├── docker-compose-tig-mqtt_context.md         # [ACTUALIZADO] Con servicio db-sync y perfiles
│   │   └── regional_event_correlator_context.md       # [ACTUALIZADO] Con sesión persistente
│   └── progress/
│       ├── 2026-08-26_contexto-agente.md
│       └── 2026-08-28_contexto-agente.md              # [NUEVO] Este documento de transición técnica
├── scripts/
│   ├── correlator/
│   │   └── regional_event_correlator.py               # [MODIFICADO] clean_session=False + RSA_CORRELATOR_CLIENT_ID
│   └── db_sync/
│       ├── Dockerfile                                 # [NUEVO] Contenedor Python 3.11-slim para utilidades
│       ├── requirements.txt                           # [NUEVO] paho-mqtt, python-dotenv, influxdb-client
│       ├── backup_events.sh                           # [NUEVO] Respaldo automático, CSV, Drive y MQTT
│       ├── restore_events.sh                          # [NUEVO] Restauración destructiva interactiva
│       └── mqtt_notify.py                             # [NUEVO] Publicador de telemetría de backup (QoS 1)
└── services/
    ├── docker-unified/
    │   ├── .env.example                               # [MODIFICADO] Variables de rol y client_id persistente
    │   └── docker-compose.yml                         # [MODIFICADO] db-sync + profiles: ["primary"] en correlator
    └── systemd/
        ├── manage_backup_timer.sh                     # [NUEVO] Gestor de instalación/control systemd portable
        ├── rsa-backup-events.service.template         # [NUEVO] Plantilla de servicio oneshot
        └── rsa-backup-events.timer.template           # [NUEVO] Plantilla de temporizador diario 02:00 UTC
```

---

## ⚙️ Configuración del Entorno y Contenedor (`rsa-db-sync`)

- **Estrategia Portable**: Se descartó la dependencia de entornos virtuales (`.venv`) locales en el host para tareas de background, adoptando en su lugar el microservicio Docker `rsa-db-sync`.
- **Imagen Base**: `python:3.11-slim` con `paho-mqtt>=1.6.1`, `python-dotenv>=1.0.0` e `influxdb-client>=1.36.0`.
- **Modo de Invocación**: Se ejecuta efímeramente bajo demanda (`docker compose run --rm db-sync mqtt_notify.py [args]`), sin servicio daemon permanente ni consumo de memoria en reposo.

---

## 🛠️ Modificaciones de Código y Validación Operativa

### 1. Respaldo y Restauración de InfluxDB (Subfase 5A.1 y 5A.2)
- **Snapshot Binario TSM**: Ejecución de `influx backup` dentro de `rsa-influxdb` para el bucket `rsa_events` empaquetado en `.tar.gz`.
- **Exportación CSV Tabular**: Consulta Flux con `pivot(rowKey: ["_time","event_id"], columnKey: ["_field"], valueColumn: "_value")` para inspección humana inmediata.
- **Sincronización y Rotación Cloud**: Subida vía `rclone copy` a `gdrive:RSA-Backups/influxdb/` y purga automática de respaldos con antigüedad superior a 7 días.
- **Validación en Servidor**: Respaldo manual ejecutado en **10 segundos**, catalogando **415 eventos** y verificando la subida a Google Drive.
- **Restauración Destructiva**: Script `restore_events.sh` con flag `--latest` o `--date`, aviso de conteo actual y prompt destructivo de confirmación explícita (`SI`).

### 2. Automatización Portable Systemd (Subfase 5A.3)
- **Cero Rutas Hardcodeadas**: Plantillas `.template` procesadas por `manage_backup_timer.sh` mediante `sed` seguro, resolviendo dinámicamente el usuario real (`SUDO_USER`), grupo primario, rutas del repositorio y binarios del host.
- **Temporizador Diario**: Programado a las `02:00:00 UTC` con `Persistent=true` y `RandomizedDelaySec=300`.
- **Validación en Servidor**: Instalado y probado con `manage_backup_timer.sh --run-now`, completando la ejecución en **11 segundos** con registro impecable en `journald` (`status=0/SUCCESS`).

### 3. Arquitectura Multi-Servidor y Resiliencia ante Apagones (Subfase 5B)
- **Control por Perfiles**: `correlator` configurado con `profiles: ["primary"]`. En `rsa-server` se levanta con `docker compose --profile primary up -d`, mientras que en `home-server` arrancará como espejo pasivo sin correlador.
- **Sesión Persistente MQTT**: Refactorización de `regional_event_correlator.py` para usar `clean_session=False` y `client_id` estático (`rsa-correlator-primary`).
- **Prueba de Resiliencia Validada**: Se apagó el correlador durante 6 minutos, se emitieron detecciones reales (`DEV0`, `CHA2`) y una simulada (`SIM01`). Al reiniciar el contenedor, Mosquitto entregó en ráfaga todas las alertas retenidas en cola en la misma fracción de segundo, confirmando tolerancia absoluta ante caídas de servicio.

---

## 📋 Pasos Sugeridos para el Siguiente Agente

1. **Despliegue en Servidor Espejo (`home-server`)**:
   - Cuando se tenga acceso físico o SSH a `home-server`, clonar el repositorio y configurar `.env` con `RSA_SERVER_ROLE=mirror`.
   - Iniciar el stack estándar: `docker compose up -d --build` (verificar que `rsa-correlator` no arranca).
   - Probar la restauración inicial del catálogo con `bash scripts/db_sync/restore_events.sh --latest`.
2. **Monitoreo de Telemetría de Respaldos**:
   - Incorporar en el panel de Node-RED o dashboard de Grafana un widget que consuma `rsa/seismic/smart/system/backup` para alertar si un respaldo diario reporta `status: "failure"`.
