---
id: ADR-016
titulo: Resolución Global de Trazas MiniSEED, Exclusión de Registro Continuo y Determinación Temporal del event_id
estado: Aceptado
fecha: 2026-08-21
temas: [event-analyzer, correlador, miniseed, influxdb, mqtt, lazy-loading, consistencia-temporal, arquitectura]
entorno: RSA-Intern-TIG-MQTT
---

# ADR-016: Resolución Global de Trazas MiniSEED, Exclusión de Registro Continuo y Determinación Temporal del event_id

## Estado

**Aceptado** | Fecha: 2026-08-21

## Contexto

Tras la culminación de la Fase 4 de integración de InfluxDB con Event Analyzer y el Correlador Regional en el stack `RSA-Intern-TIG-MQTT`, el análisis detallado de datos reales reveló tres inconsistencias arquitectónicas y de flujo de datos:

1. **Filtro restrictivo de estaciones en Event Analyzer**: En InfluxDB, el campo `stations` del evento almacena únicamente las estaciones que dispararon la alerta ($\ge 2$ estaciones dentro de la ventana de coincidencia de 10 s). En `app.py`, este conjunto se pasaba directamente como filtro a `reader.scan_event(stations=stations_target)`. Como consecuencia, el visualizador ignoraba las trazas MiniSEED de las demás estaciones de la red que sí habían recortado y subido el evento tras recibir el comando broadcast de extracción masiva.
2. **Contaminación por datos de registro continuo**: La búsqueda recursiva de archivos MiniSEED mediante patrones glob `**/*.mseed` en `/data/events` resolvía tanto los recortes de eventos ubicados en `ESTACION/events/` como los bloques de registro continuo continuo ubicados en `ESTACION/mseed/`, generando duplicaciones espurias de trazas en la visualización.
3. **Desfase temporal arbitrario en el `event_id`**: El Correlador Regional generaba el identificador del evento (`event_id = corr-YYYYMMDD-HHMMSS`) utilizando `datetime.now()` (reloj del servidor en el instante de ejecución), mientras que el timestamp `_time` en InfluxDB se asignaba con base en `dt_min` (la detección más temprana). Esto creaba un desfase de varios segundos entre el ID del evento, la hora registrada en la base de datos y el timestamp del archivo MiniSEED en disco (`dt_min - 60s`), haciendo contraintuitiva la navegación y correlación para el operador sismológico.
4. **Ambigüedad en métricas de la interfaz**: La UI etiquetaba `(N est.)` en el selector de eventos, interpretándose erróneamente como la cantidad de trazas disponibles en disco en lugar de estaciones detectoras de la correlación.

## Opciones Evaluadas

### Opción A: Mantener el Filtro de InfluxDB y Hora de Procesamiento
- **Ventajas:** No requiere modificar la lógica de `app.py` ni el script del correlador.
- **Desventajas:** 
  - Impide al operador evaluar la propagación de la onda sísmica en toda la red de estaciones.
  - Mantiene trazas duplicadas provenientes del registro continuo.
  - Preserva identificadores con desfases temporales incoherentes respecto a los datos físicos.

### Opción B: Desacoplamiento de Estaciones Detectoras/Resueltas, Segmentación de Rutas `/events/` y `event_id` Determinista por `dt_min` (Seleccionada)
- **Ventajas:**
  - **Resolución Completa de Trazas**: Al pasar `stations=None` a `scan_event()`, se localizan y cargan las trazas de todas las estaciones que respondieron al broadcast en la ventana temporal ($\pm 120$ s).
  - **Aislamiento de Registro Continuo**: Restricción del patrón glob a `*/events/*.mseed`, garantizando que únicamente se lean recortes legítimos de eventos.
  - **Coherencia Temporal Unívoca**: El `event_id` se genera a partir de `dt_min.strftime('%Y%m%d-%H%M%S')`, alineando perfectamente el ID, el campo `_time` en InfluxDB y el nombre del archivo en disco (`dt_min - 60s`).
  - **Claridad Operativa en UI**: Diferenciación explícita entre "Estaciones Detectoras" (`n_stations` de InfluxDB) y "Estaciones Resueltas" (`len(available_stations)` en disco).
- **Desventajas:**
  - Los eventos previamente registrados en InfluxDB quedan con el formato antiguo de `event_id` y requieren una migración puntual (borrado y reescritura controlada).

## Decisión

Se eligió la **Opción B**:

1. **Desacoplamiento en Event Analyzer (`app.py`)**:
   - `stations_target` se renombra a `detecting_stations` como dato informativo de auditoría para metadatos y badges.
   - `reader.scan_event()` se invoca con `stations=None` para descubrir todas las estaciones con trazas en la ventana temporal del evento.
   - Actualización de etiquetas en la UI: `(N det.)` en el selector y métrica dual `Estaciones Resueltas (M/M) | Detectoras: EST1, EST2`.
2. **Segmentación de Búsqueda de Archivos (`reader.py`)**:
   - Ajuste de patrones glob en `scan()` y `scan_event()` a `*/events/*.mseed` y `*/events/*.MSEED`, excluyendo explícitamente la subcarpeta `/mseed/` de registro continuo.
3. **Generación Determinista de IDs en Correlador (`regional_event_correlator.py`)**:
   - Sustitución de `datetime.now(timezone.utc)` por `dt_min` para la construcción de `req_id` y `event_id` (`corr-{dt_min.strftime('%Y%m%d-%H%M%S')}`).
4. **Plan de Migración Retroactiva en InfluxDB**:
   - Implementación de un script puntual (`scripts/db_sync/fix_event_ids.py`) para recalcular y reescribir los `event_id` existentes en el bucket `rsa_events` a partir de su `_time` original, precedido por un respaldo de seguridad del bucket.

## Consecuencias

- **Positivas:**
  - El sismólogo puede analizar la forma de onda en todas las estaciones disponibles de la red para cada evento regional.
  - Se eliminan por completo las trazas duplicadas causadas por lecturas de registro continuo.
  - Relación matemática y visual directa: `event_id` = Hora del evento; `archivo.mseed` = `event_id - 60s`.
  - La interfaz de usuario refleja con precisión el estado de la red (estaciones que alertaron vs estaciones con datos).
  - Se completó y validó la migración retroactiva de 165 eventos históricos en InfluxDB sin pérdida ni duplicación de datos.
- **Negativas / Trabajo Futuro:**
  - Proceder con la Fase 5 (Protocolo de Respaldo y Recuperación automatizada de eventos).

## Referencias

- Diagnóstico técnico: [diagnostico_event_analyzer.md](file:///home/rsa/.gemini/antigravity-ide/brain/c712e0e0-0785-49f1-89a0-3efc836941a3/diagnostico_event_analyzer.md)
- Plan de implementación: [docs/blueprints/2026-08-21_event_analyzer_correlator_fixes_implementation_plan.md](file:///home/rsa/git/montajes/server-ubuntu/rsa/RSA-Intern-TIG-MQTT/docs/blueprints/2026-08-21_event_analyzer_correlator_fixes_implementation_plan.md)
- Contexto técnico fix_event_ids: [docs/context/fix_event_ids_context.md](file:///home/rsa/git/montajes/server-ubuntu/rsa/RSA-Intern-TIG-MQTT/docs/context/fix_event_ids_context.md)
- Contexto técnico Event Analyzer: [docs/context/event_analyzer_context.md](file:///home/rsa/git/montajes/server-ubuntu/rsa/RSA-Intern-TIG-MQTT/docs/context/event_analyzer_context.md)
- Contexto técnico Correlador: [docs/context/regional_event_correlator_context.md](file:///home/rsa/git/montajes/server-ubuntu/rsa/RSA-Intern-TIG-MQTT/docs/context/regional_event_correlator_context.md)
- ADR previo de integración: [ADR-015: Índice Centralizado de Eventos Sísmicos en InfluxDB](file:///home/rsa/git/rsa/RSA-Metodologias/decisiones/015_indice_eventos_sismicos_influxdb_clasificacion_mqtt.md)
