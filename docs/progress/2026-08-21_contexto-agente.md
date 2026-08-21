# Resumen de Sesión: Diagnóstico de Resolución de Trazas, Exclusión de Registro Continuo y Plan de Acción

**Fecha**: 2026-08-21  
**Repositorio**: `RSA-Intern-TIG-MQTT`  
**Agente de IA**: Antigravity  
**Usuario**: Milton  

---

## 🎯 Objetivo de la Sesión

Diagnosticar, analizar y planificar la solución integral a 4 problemas técnicos y de consistencia temporal identificados en el ecosistema de eventos sísmicos (Event Analyzer, InfluxDB y Correlador Regional) antes de avanzar a la Fase 5. Se documentaron formalmente el **ADR-016** y el **Plan de Implementación en 4 pasos** con checkpoints de verificación manual.

---

## 📂 Estructura del Repositorio Implementada

```text
RSA-Intern-TIG-MQTT/
├── docs/
│   ├── adr/
│   │   └── 016_resolucion_global_trazas_y_determinacion_temporal_event_id.md   # [NUEVO] ADR local de decisiones arquitectónicas
│   ├── blueprints/
│   │   ├── 2026-08-13_influx_sync_implementation_plan.md                      # Blueprint maestro de sincronización InfluxDB-MQTT
│   │   └── 2026-08-21_event_analyzer_correlator_fixes_implementation_plan.md  # [NUEVO] Plan de acción y checkpoints de fixes
│   ├── context/
│   │   ├── docker-compose-nodered_context.md
│   │   ├── docker-compose-tig-mqtt_context.md
│   │   ├── event_analyzer_context.md
│   │   ├── influx_client_context.md
│   │   └── regional_event_correlator_context.md
│   └── progress/
│       ├── 2026-08-19_contexto-agente.md
│       └── 2026-08-21_contexto-agente.md                                      # [NUEVO] Este documento de transición técnica
```

---

## ⚙️ Configuración del Entorno Virtual y Servicios

- **Stack Docker Unificado (`services/docker-unified`)**:
  - `rsa-influxdb`: InfluxDB 2.7 administrando bucket `rsa_events` (retención infinita).
  - `rsa-telegraf`: Telegraf 1.28 con consumidor `json_v2` y preservación estricta de `timestamp_utc`.
  - `rsa-correlator`: Correlador regional Python 3.11 (`paho-mqtt`).
  - `rsa-event-analyzer`: Streamlit (:8501) + Dash Resampler (:8050) sobre Python 3.11 (`obspy`, `plotly`, `influxdb-client`).
- **Google Drive (`/data/events`)**:
  - Subcarpeta `ESTACION/events/`: Recortes de eventos sísmicos disparados por broadcast / manuales.
  - Subcarpeta `ESTACION/mseed/`: Bloques de datos de registro continuo gestionados localmente por cada acelerógrafo (no deben ser leídos por Event Analyzer).

---

## 🛠️ Modificaciones de Código y Refactorización

En esta sesión se mantuvo la directriz de análisis y diseño arquitectónico previo a la codificación:

### 1. Diagnóstico de los 4 Problemas Técnicos
- **Problema 1A (Filtro restrictivo de estaciones)**: `app.py` pasaba `stations_target` (solo las $\ge 2$ estaciones detectoras en InfluxDB) a `reader.scan_event()`, impidiendo evaluar el sismo en las demás estaciones que sí subieron recortes vía broadcast.
- **Problema 1B (Desfase temporal del `event_id`)**: El correlador generaba `event_id` con `datetime.now()` (hora de procesamiento), creando un desfase de 3 a 11 segundos con respecto a la hora real del evento (`_time` / `dt_min`) y a las trazas en disco (`dt_min - 60s`).
- **Problema 2 (Contaminación de registro continuo)**: `reader.py` usaba `**/*.mseed` recursivo, leyendo accidentalmente archivos de la subcarpeta `/mseed/` como si fueran eventos.
- **Problema 3 (Métricas ambiguas en UI)**: El selector mostraba `(N est.)` interpretándose erróneamente como trazas en disco en lugar de estaciones detectoras.
- **Problema 4 (Inconsistencia histórica)**: Los eventos ya almacenados en InfluxDB conservan `event_id` antiguos que requieren migración retroactiva.

### 2. Decisiones Arquitectónicas Formalizadas
- Formalizado el **ADR-016** tanto en el repositorio institucional (`RSA-Metodologias`) como en la raíz local del proyecto (`docs/adr/`).
- Copiado y respaldado el plan de acción en `docs/blueprints/2026-08-21_event_analyzer_correlator_fixes_implementation_plan.md`.

---

## 📋 Pasos Sugeridos para el Siguiente Agente

El siguiente agente debe proceder directamente con la ejecución secuencial del plan de fixes:

1. **Paso 1 — Segmentar búsqueda en `reader.py`**:
   - Modificar `scan_event()` y `scan()` para usar `os.path.join(self.data_dir, "*", "events", f"*{d_str}*.mseed")`.
2. **Paso 2 — Desacoplar estaciones y actualizar UI en `app.py`**:
   - Invocar `reader.scan_event(ref_time=ref_dt, stations=None, window_s=120.0)`.
   - Renombrar `stations_target` a `detecting_stations` para uso en badges y metadatos.
   - Actualizar etiquetas: `(N det.)` en selector y métrica `Estaciones Resueltas (M/M) | Detectoras: EST1, EST2`.
   - Solicitar al usuario reconstruir el contenedor `event-analyzer` y validar en `http://<IP>:8501` (**Checkpoint 2**).
3. **Paso 3 — Unificar `event_id` con `dt_min` en `regional_event_correlator.py`**:
   - Cambiar `req_id = f"corr-{dt_min.strftime('%Y%m%d-%H%M%S')}"`.
   - Solicitar reconstruir contenedor `correlator` y validar en InfluxDB (**Checkpoint 3**).
4. **Paso 4 — Migración retroactiva en InfluxDB (`scripts/db_sync/fix_event_ids.py`)**:
   - Crear script de migración para recalcular `event_id` de eventos históricos a partir de `_time`.
   - Ejecutar backup previo de seguridad y correr migración (**Checkpoint 4**).
5. **Avanzar a la Fase 5**:
   - Desarrollar `backup_events.sh` y `restore_events.sh` para sincronización con Google Drive (`rclone`).
