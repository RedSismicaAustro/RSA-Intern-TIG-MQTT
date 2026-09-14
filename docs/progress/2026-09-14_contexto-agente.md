# Resumen de Sesión: Implementación del Modelo Jerárquico de Alertas, Filas Colapsables en Grafana, Simulador Aislado MQTT y Documentación Federada

**Fecha**: 2026-09-14  
**Repositorio**: `RSA-Intern-TIG-MQTT`  
**Agente de IA**: Antigravity  
**Usuario**: Milton Muñoz  

---

## 🎯 Objetivo de la Sesión

Implementar, afinar y validar exhaustivamente en el Stack TIG las 4 fases del plan de arquitectura de alertas y visualización centralizada de la Red Sísmica del Austro:
1. Configurar la ingesta de telemetría especializada en Telegraf (`station_acquisition`, `station_sensor`, `station_drive`).
2. Implementar en `SeismicMonitor` el motor de votación jerárquica en Flux para eliminar ambigüedades diagnósticas y presentar una matriz limpia de 3 columnas con enlaces contextuales.
3. Reorganizar el dashboard `Health` en 4 filas temáticas colapsables por defecto para erradicar la sobrecarga visual ("apretujamiento de información") y optimizar el consumo de consultas en InfluxDB.
4. Desarrollar un simulador de pruebas sintéticas MQTT en Python con aislamiento garantizado mediante publicación simultánea de 5 canales y marcas de tiempo UTC ISO 8601 dinámicas.
5. Formalizar la documentación técnica generando 4 archivos de contexto técnico, registrando el ADR-019 y actualizando los índices federados del exocortex de la RSA.

---

## 📂 Estructura del Repositorio Implementada

```text
RSA-Intern-TIG-MQTT/
├── docs/
│   ├── adr/
│   │   ├── 016_resolucion_global_trazas_y_determinacion_temporal_event_id.md
│   │   ├── 017_respaldo_influxdb_y_arquitectura_multiservidor_con_sesion_persistente_mqtt.md
│   │   └── 019_modelo_jerarquico_alertas_y_visualizacion_grafana.md        # [NUEVO] ADR local consolidado
│   ├── context/
│   │   ├── health_context.md                                               # [NUEVO] Contexto dashboard Health v9
│   │   ├── seismic_monitor_context.md                                      # [NUEVO] Contexto dashboard SeismicMonitor v8
│   │   ├── simulador_alertas_mqtt_context.md                               # [NUEVO] Contexto simulador de pruebas
│   │   └── telegraf_context.md                                             # [NUEVO] Contexto configuración Telegraf
│   └── progress/
│       ├── 2026-09-10_contexto-agente.md
│       └── 2026-09-14_contexto-agente.md                                   # [NUEVO] Documento de transición técnica
├── scripts/
│   └── testing/
│       ├── ejecutar_simulador.sh                                           # [NUEVO] Wrapper Bash con venv efímero y trap
│       ├── requirements.txt                                                # [NUEVO] paho-mqtt>=1.6.1
│       └── simulador_alertas_mqtt.py                                       # [NUEVO] Inyector interactivo/aislado 5 canales
└── services/
    ├── docker-unified/
    │   └── telegraf.conf                                                   # [MODIFICADO] Ingesta acquisition, sensor y drive
    └── grafana/
        └── provisioning/
            └── dashboards/
                ├── health.json                                             # [MODIFICADO] v9: 4 filas colapsables, Throttled texto
                └── seismic_monitor.json                                    # [MODIFICADO] v8: Matriz 3 cols, votación Flux jerárquica
```

---

## ⚙️ Configuración del Entorno Virtual (`/tmp/rsa_simulator_venv`)

Para la ejecución de pruebas sintéticas sin contaminar el entorno global del anfitrión ni dejar procesos huérfanos, se implementó una estrategia de entorno virtual efímero orquestado por `ejecutar_simulador.sh`:
- **Directorio Venv**: `/tmp/rsa_simulator_venv`
- **Versión de Python**: Python 3.11 nativo del sistema
- **Dependencias Instaladas**: `paho-mqtt>=1.6.1`
- **Garantía de Cierre Limpio**: Uso de `trap cleanup EXIT` en Bash que asegura la desactivación incondicional del entorno virtual (`deactivate`) al finalizar el simulador, sin importar si termina normalmente, por error o mediante interrupción del usuario (`Ctrl+C` o `q`).

---

## 🛠️ Modificaciones de Código y Refactorización

### 1. Ingesta de Telemetría Especializada (`telegraf.conf`)
- Añadidos tres bloques dedicados `[[inputs.mqtt_consumer]]` con QoS 1:
  - `station_acquisition` en `rsa/seismic/smart/+/status/acquisition` (tags: `station_id`, `status`, `reason`; campos: `age_seconds`, `threshold_seconds`).
  - `station_sensor` en `rsa/seismic/smart/+/status/sensor` (tags: `station_id`, `status`, `clock_source`, `reason`; campos: `ax`, `ay`, `az`, `clock_error`).
  - `station_drive` en `rsa/seismic/smart/+/status/drive` (tags: `station_id`, `status`, `reason`; campos: `pending_mseed`, `failed_uploads_protected`, `free_disk_percent`).
- Declaración estricta de cadenas en `json_string_fields` y `tag_keys` para prevenir fallos de tipado numérico.

### 2. Motor de Votación Jerárquico Flux (`seismic_monitor.json` - v8)
- Implementada la consulta Flux unificada que calcula 7 flujos de severidad ponderada en paralelo:
  - `Offline` (peso 6, dark-red)
  - `Adquisicion` (peso 5, dark-red, falla de watchdog `age_seconds > 300s`)
  - `Sensor` (peso 4, dark-red, falla física en reposo fuera de $9.81 \pm 0.8\text{ m/s}^2$)
  - `Disco` (peso 3 crítico $>95\%$, peso 2 advertencia $>90\%$, dark-orange)
  - `Drive` (peso 2, semi-dark-yellow, $>3$ pendientes o warning)
  - `Temperatura` (peso 1, dark-orange, $>70^\circ\text{C}$)
  - `Memoria` (peso 1, dark-orange, $>90\%$)
  - `OK` (peso 0, green)
- Agregación con `union()`, ordenamiento descendente y `limit(n: 1)` para derivar un diagnóstico único por estación.
- Tabla compacta de 3 columnas (`Estación`, `Conectividad`, `Diagnóstico Principal`) con color degradado en toda la fila (`applyToRow: true`) y Data Links activos hacia el dashboard `Health`.
- **Desvinculación de Throttled**: Desacoplado de las alertas del monitor para erradicar falsos positivos por fluctuaciones térmicas habituales en hardware embebido.
- **Ajuste de Umbral de Disco**: Calibrado estrictamente para activar alerta únicamente cuando el uso supere el 90%.

### 3. Reorganización en Filas Colapsables (`health.json` - v9)
- Corrección de la estructura interna del JSON: se encapsularon los 18 paneles dentro del arreglo `row.panels` de 4 filas temáticas colapsables por defecto (`collapsed: true`):
  - Fila 30: *Salud del Sistema y Hardware (Raspberry Pi)*
  - Fila 20: *Salud de Adquisición (Ring Buffer Watchdog)*
  - Fila 23: *Integridad del Sensor Acelerométrico y Reloj*
  - Fila 26: *Sincronización con Google Drive*
- El panel de Throttled se convirtió en un indicador puramente informativo de texto sin colores de alerta en rojo.
- Umbrales del histórico de disco ajustados a 90% (advertencia) y 95% (crítico).
- Decisión técnica sobre navegación: Mantener filas colapsadas para ser abiertas manualmente por el operador tras navegar desde `SeismicMonitor` (`var-station=...`), debido a que Grafana v11 no expande dinámicamente paneles hijos en URLs directas (`viewPanel`).

### 4. Simulador Interactivo de Alertas MQTT (`simulador_alertas_mqtt.py`)
- Implementación de 8 escenarios de prueba automatizados.
- **Mecanismo de Aislamiento de 5 Canales**: Cada escenario inyecta simultáneamente los 5 tópicos de telemetría (`state`, `health`, `acquisition`, `sensor`, `drive`), transmitiendo 4 canales nominales limpios y únicamente 1 canal con la anomalía evaluada. Esto erradica traslapes causados por mensajes retenidos previos en el broker o telemetría periódica de hardware de prueba (`TEST`).
- Generación de hora UTC dinámica en ISO 8601 (`get_current_iso_time()`) al segundo exacto.
- Soporte para modo interactivo (pausa guiada con `Enter`), ejecución puntual (`-e <num>`) y listado CLI (`--list`).

### 5. Documentación y Memoria Semántica
- **Contextos Técnicos**: Generados 4 documentos estandarizados en `docs/context/` (`telegraf_context.md`, `seismic_monitor_context.md`, `health_context.md`, `simulador_alertas_mqtt_context.md`).
- **Arquitectura de Decisiones**: Redactado y aprobado `ADR-019` (*Modelo Jerárquico de Alertas y Visualización Centralizada de Estaciones en Grafana*), registrado tanto en `RSA-Metodologias` como en `RSA-Intern-TIG-MQTT/docs/adr/`.
- **Índice Federado**: Actualizado `rsa/RSA-Metodologias/indice/indice_tematico.md` con los 4 nuevos contextos técnicos, el ADR-019 y marcando el diagnóstico `2026-09-09` como resuelto.

---

## 📋 Pasos Sugeridos para el Siguiente Agente

1. **Reinicio de Servicios en el Servidor Ubuntu (Delegação al Operador)**:
   - Si los contenedores de Telegraf y Grafana no han sido reiniciados en el servidor tras las modificaciones de aprovisionamiento, solicitar al usuario que ejecute:
     ```bash
     docker compose restart telegraf grafana
     ```
   - Verificar logs de arranque para confirmar carga limpia sin errores sintácticos.
2. **Auditoría Visual en Navegador Web**:
   - Abrir `SeismicMonitor` en Grafana (`:3000`) y confirmar que la tabla muestra las 3 columnas en verde nominal para estaciones activas.
   - Navegar a `Health` seleccionando cualquier estación y validar que las 4 filas temáticas aparecen colapsadas y se despliegan suavemente al expandirlas.
3. **Gestión de Commits en Repositorios Locales**:
   - Registrar los cambios en `RSA-Intern-TIG-MQTT` y en `RSA-Metodologias` sugiriendo los mensajes de commit en minúsculas y prefijados por el tipo, de acuerdo a la normativa institucional.
4. **Volcado de Bitácora de Sesión**:
   - Ejecutar el volcado de bitácora personal con la skill `volcado_bitacora` para persistir la narrativa cronológica de esta sesión en `RSA-Bitacora-LLM-Milton`.
