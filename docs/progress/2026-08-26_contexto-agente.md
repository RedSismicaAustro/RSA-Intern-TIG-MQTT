# Resumen de Sesión: Diagnóstico Técnico, Diseño Arquitectónico y Plan de Implementación de la Fase 5 (Respaldo, Recuperación y Multi-Servidor)

**Fecha**: 2026-08-26  
**Repositorio**: `RSA-Intern-TIG-MQTT`  
**Agente de IA**: Antigravity  
**Usuario**: Milton  

---

## 🎯 Objetivo de la Sesión

Analizar integralmente los requerimientos, riesgos y escenarios de falla para la **Fase 5** (Protocolo de Respaldo y Recuperación de InfluxDB), definir la arquitectura multi-servidor (`rsa-server` primario vs `home-server` espejo pasivo) ante cortes de energía prolongados (escenario R4), y estructurar el **Plan de Implementación** formal en 4 subfases (5A.1, 5A.2, 5A.3 y 5B) con 22 checkpoints de validación.

---

## 📂 Estructura del Repositorio Implementada

```text
RSA-Intern-TIG-MQTT/
├── docs/
│   ├── blueprints/
│   │   ├── 2026-08-13_influx_sync_implementation_plan.md                      # Plan maestro original
│   │   ├── 2026-08-21_event_analyzer_correlator_fixes_implementation_plan.md  # Plan ejecutado de fixes ADR-016
│   │   └── 2026-08-26_fase5_implementation_plan.md                           # [NUEVO] Plan detallado ejecutable Fase 5
│   └── progress/
│       ├── 2026-08-25_contexto-agente.md
│       └── 2026-08-26_contexto-agente.md                                      # [NUEVO] Este documento de transición técnica
├── scripts/
│   ├── correlator/
│   │   └── regional_event_correlator.py                                       # [POR MODIFICAR en 5B] client_id fijo + clean_session=False
│   └── db_sync/
│       ├── fix_event_ids.py                                                   # Script de migración ejecutado en sesión previa
│       ├── backup_events.sh                                                   # [POR CREAR en 5A.2] Snapshot binario + CSV + Drive + rotación
│       ├── restore_events.sh                                                  # [POR CREAR en 5A.2] Descarga + restauración destructiva
│       ├── mqtt_notify.py                                                     # [POR CREAR en 5A.2] Helper Python para notificación MQTT
│       └── requirements.txt                                                   # [POR CREAR en 5A.1] paho-mqtt, python-dotenv, influxdb-client
└── services/
    ├── docker-unified/
    │   ├── .env.example                                                       # [POR MODIFICAR en 5B] RSA_SERVER_ROLE, RSA_CORRELATOR_CLIENT_ID
    │   └── docker-compose.yml                                                 # [POR MODIFICAR en 5B] profiles: ["primary"] en correlator
    └── systemd/
        ├── rsa-backup-events.service                                          # [POR CREAR en 5A.3] Unidad systemd del backup
        └── rsa-backup-events.timer                                            # [POR CREAR en 5A.3] Timer systemd diario 02:00 UTC
```

---

## ⚙️ Configuración del Entorno Virtual (`scripts/db_sync/.venv`)

- **Propósito**: Aislar las dependencias de ejecución para scripts de mantenimiento y sincronización en el host (`mqtt_notify.py`, `fix_event_ids.py`) sin depender de paquetes del sistema operativo ni de contenedores Docker para tareas livianas.
- **Dependencias**:
  - `paho-mqtt>=1.6.1`: Publicación de estado de respaldos al tópico `rsa/seismic/smart/system/backup`.
  - `python-dotenv>=1.0.0`: Carga dinámica de credenciales y configuración desde `.env`.
  - `influxdb-client>=1.36.0`: Consultas analíticas Flux y verificación de buckets.
- **Estrategia de Ejecución**: Los scripts Bash (`backup_events.sh`, `restore_events.sh`) invocarán el intérprete directamente mediante `$SCRIPT_DIR/.venv/bin/python`.

---

## 🛠️ Modificaciones de Código y Decisiones Técnicas

Durante la sesión se analizaron y acordaron las siguientes definiciones arquitectónicas:

### 1. Alcance y Estrategia de Respaldo (Fase 5A)
- **Bucket Exclusivo**: Respaldo focalizado en `rsa_events` (metadatos no recuperables con retención infinita). Se excluye `telemetry` (retención de 90 días, regenerable desde MQTT).
- **Snapshot Binario + Exportación CSV**: Uso primario de `influx backup` (formato nativo) complementado con una exportación CSV vía consulta Flux `pivot()` para análisis interno y procesamiento de datos tabulares.
- **Rotación y Retención**: Conservación estricta de los últimos 7 días con purga automática tanto local como en Google Drive (`rclone deletefile`).
- **Automatización**: Programación mediante `systemd timer` (`Persistent=true`, `OnCalendar=02:00:00 UTC`, `RandomizedDelaySec=300`) y unidad `service` tipo `oneshot`.
- **Notificación MQTT Dinámica**: Emisión de telemetría de respaldo al tópico `rsa/seismic/smart/system/backup` con QoS 1, resolviendo dinámicamente el identificador de servidor mediante `${TELEGRAF_CLIENT_ID}` (sin variables hardcodeadas).

### 2. Arquitectura Multi-Servidor ante Cortes de Energía (Fase 5B y Escenario R4)
- **Nomenclatura**: `rsa-server` (servidor de oficina, primario) y `home-server` (servidor doméstico, espejo pasivo).
- **Prevención de Duplicación del Correlador**: Se implementará control por `profiles: ["primary"]` en Docker Compose. En `rsa-server` se desplegará con `--profile primary`, mientras que en `home-server` se ejecutará sin perfil, impidiendo la instanciación redundante del contenedor `rsa-correlator`.
- **Retención de Detecciones en el Broker**: Para evitar la pérdida de eventos cuando `rsa-server` esté offline por cortes de luz, se modificará `regional_event_correlator.py` para usar un `client_id` estático (`RSA_CORRELATOR_CLIENT_ID`) y sesión persistente (`clean_session=False`).
- **Propagación Natural de Clasificaciones Tipo 3/4**: Se verificó que [`influx_client.py`](file:///home/rsa/git/montajes/server-ubuntu/rsa/RSA-Intern-TIG-MQTT/services/event-analyzer/src/core/influx_client.py#L237) ya emite clasificaciones con QoS 1 al tópico de metadatos, por lo que las confirmaciones/descartes efectuados en `home-server` se sincronizan automáticamente en `rsa-server` vía Telegraf sin requerir un motor de *merge* inteligente.

---

## 📋 Pasos Sugeridos para el Siguiente Agente

El siguiente agente debe iniciar la ejecución secuencial del plan de acción definido en [`docs/blueprints/2026-08-26_fase5_implementation_plan.md`](file:///home/rsa/git/montajes/server-ubuntu/rsa/RSA-Intern-TIG-MQTT/docs/blueprints/2026-08-26_fase5_implementation_plan.md):

1. **Ejecutar Subfase 5A.1 (Prerrequisitos)**:
   - Crear `scripts/db_sync/requirements.txt`.
   - Guiar al usuario para crear el entorno virtual `.venv` en `scripts/db_sync/` e instalar dependencias.
   - Validar checkpoints C1 a C5 (`rclone`, carpeta `RSA-Backups/influxdb/` en Drive, Docker sin sudo, InfluxDB CLI).
2. **Ejecutar Subfase 5A.2 (Scripts Core)**:
   - Implementar `scripts/db_sync/mqtt_notify.py`.
   - Implementar `scripts/db_sync/backup_events.sh` (con manejo de errores, export CSV, rclone y purga >7 días).
   - Implementar `scripts/db_sync/restore_events.sh` (con flag `--latest`, `--date` y confirmación destructiva).
   - Validar checkpoints C6 a C11 mediante pruebas manuales en `rsa-server`.
3. **Ejecutar Subfase 5A.3 (Automatización con systemd)**:
   - Crear `services/systemd/rsa-backup-events.service` y `rsa-backup-events.timer`.
   - Guiar al usuario en la instalación, habilitación y verificación de logs en `journalctl` (checkpoints C12 a C15).
4. **Ejecutar Subfase 5B (Configuración Multi-Servidor)**:
   - Actualizar `.env.example` con `RSA_SERVER_ROLE` y `RSA_CORRELATOR_CLIENT_ID`.
   - Actualizar `services/docker-unified/docker-compose.yml` con `profiles: ["primary"]` en `correlator`.
   - Refactorizar `regional_event_correlator.py` para habilitar `clean_session=False`.
   - Validar checkpoints C16 a C22.
