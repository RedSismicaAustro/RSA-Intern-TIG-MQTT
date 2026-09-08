# Resumen de Sesión: Depuración, Migración de Estaciones en InfluxDB v2 y Optimización de Dashboards de Grafana

**Fecha**: 2026-09-08  
**Repositorio**: `RSA-Intern-TIG-MQTT`  
**Agente de IA**: Antigravity  
**Usuario**: Milton  

---

## 🎯 Objetivo de la Sesión

Ejecutar el saneamiento y normalización integral de la base de datos de telemetría y catálogo de eventos en el servidor central:
1. Eliminar definitivamente todas las series temporales de estaciones obsoletas o dadas de baja (`ACL1`, `SIM01`, `TEST01`, `TEST02`).
2. Migrar y renombrar deterministamente el histórico de telemetría y metadatos de eventos para estaciones que cambiaron de identificador (`DEV01` ➔ `TEST`, `TEN01`/`TEN1` ➔ `TENG`).
3. Resolver anomalías visuales en los dashboards aprovisionados de Grafana (`SeismicMonitor` y `Health`).

---

## 📂 Estructura del Repositorio Implementada

```text
RSA-Intern-TIG-MQTT/
├── docs/
│   └── progress/
│       ├── 2026-08-28_contexto-agente.md
│       └── 2026-09-08_contexto-agente.md              # [NUEVO] Documento de transición técnica
├── scripts/
│   └── db_sync/
│       ├── Dockerfile
│       ├── backup_events.sh
│       ├── fix_event_ids.py
│       ├── migrate_stations.py                        # [NUEVO] Script de migración y purga segura
│       ├── mqtt_notify.py
│       ├── requirements.txt
│       └── restore_events.sh
└── services/
    └── grafana/
        └── provisioning/
            └── dashboards/
                ├── health.json                        # [MODIFICADO] Variable station con regex y opciones pre-pobladas (v3)
                └── seismic_monitor.json               # [MODIFICADO] Agrupación por station_id previa a last()
```

---

## ⚙️ Configuración del Entorno y Ejecución Portable (`rsa-db-sync`)

- **Entorno de Ejecución**: Toda la operación de migración y consulta en InfluxDB se ejecutó de forma portable mediante el microservicio contenedor `rsa-db-sync` (`docker compose run --rm db-sync ...`), eliminando dependencias locales en el host.
- **Resiliencia ante Límites de Retención (Retention Policy)**: InfluxDB v2 rechaza con código HTTP `422 (Unprocessable Entity)` escrituras con timestamps anteriores al límite inferior de retención (`90d`). El script `migrate_stations.py` fue provisto de detección automática de retención y una función `safe_write_batch` para descartar puntos expirados sin interrumpir la migración del bloque vigente.

---

## 🛠️ Modificaciones de Código y Resultados Operativos

### 1. Eliminación Definitiva de Estaciones Obsoletas
- Se ejecutó el borrado mediante la API de predicados de InfluxDB v2 en el bucket `telemetry` para `ACL1`, `SIM01`, `TEST01` y `TEST02`.
- Verificación Flux confirmó que no quedó ningún registro en base de datos.

### 2. Migración y Renombrado de Estaciones (`migrate_stations.py`)
- Se implementó el script portable `migrate_stations.py` con soporte `--dry-run` para previsualización segura.
- **Telemetría Migrada**:
  - `DEV01` ➔ `TEST`: 155.128 puntos reescritos y purgados.
  - `TEN01` ➔ `TENG`: 75.265 puntos reescritos y purgados.
  - `TEN1` ➔ `TENG`: 6.304 puntos reescritos y purgados.
  - **Total de puntos de telemetría procesados**: **234.439 puntos** (los ~2.200 puntos que habían superado los 90 días fueron descartados limpiamente).
- **Catálogo de Eventos (`rsa_events`)**:
  - 12 eventos históricos multidetección actualizados de forma determinista (`DEV0,TEST`, `CHA2,TEST`, `TEST,FERR`), preservando sus identificadores `event_id`, timestamps y estructura JSON.

### 3. Optimización de Dashboards en Grafana
- **`SeismicMonitor` (`seismic_monitor.json`)**:
  - Se corrigió la consulta Flux agregando `|> group(columns: ["station_id"])` **antes** de `|> last()`. Esto resolvió la anomalía de filas duplicadas para `TENG` originadas por múltiples claves de series históricas.
- **`Health` (`health.json`)**:
  - Se configuró la variable `station` con opciones pre-pobladas para las 6 estaciones activas (`CHA1`, `CHA2`, `DEV0`, `FERR`, `TENG`, `TEST`), `schema.tagValues` con ventana de 7 días y filtro regex estricto `/^(CHA1|CHA2|DEV0|FERR|TENG|TEST)$/`.
  - Se incrementó la versión a `version: 3` garantizando que Grafana sobrescriba la caché interna de aprovisionamiento.

---

## 📋 Pasos Sugeridos para el Siguiente Agente

1. **Monitoreo de Telemetría `status/acquisition` (Backlog Diagnóstico 2026-09-02)**:
   - Abordar la ingesta del tópico `rsa/seismic/smart/+/status/acquisition` en `telegraf.conf` (medición `station_acquisition`).
   - Crear el panel semáforo y curvas de latencia (`age_seconds`) en Grafana según el documento [`docs/analysis/2026-09-02_diagnostico_ingesta_telemetria_status_acquisition.md`](../analysis/2026-09-02_diagnostico_ingesta_telemetria_status_acquisition.md).
2. **Respaldo Periódico**:
   - Verificar la ejecución automática del timer diario de respaldo (`rsa-backup-events.timer`) a las 02:00 UTC para asegurar que el nuevo estado migrado se respalde en Google Drive.
