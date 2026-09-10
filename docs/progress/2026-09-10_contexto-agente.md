# Resumen de Sesión: Modelo Jerárquico de Alertas y Arquitectura de Visualización Centralizada en Grafana

**Fecha**: 2026-09-10  
**Repositorio**: `RSA-Intern-TIG-MQTT`  
**Agente de IA**: Antigravity  
**Usuario**: Milton Muñoz  

---

## 🎯 Objetivo de la Sesión

Diseñar y formalizar la arquitectura de visualización y monitoreo centralizado de alertas para la red acelerográfica de la RSA en el Stack TIG:
1. Eliminar la ceguera operativa del monitor 24/7 (`SeismicMonitor`), que operaba bajo un esquema binario de conexión (`online`/`offline`) ignorando paradas silenciosas de adquisición, incoherencias físicas del acelerómetro o fallos de sincronización con Google Drive.
2. Definir una taxonomía jerárquica estricta basada en criticidad sismológica: **Rojo (Crítico - pérdida o corrupción de datos)**, **Amarillo (Advertencia - atención sin pérdida inmediata)** y **Verde (Nominal)**.
3. Consolidar el diagnóstico técnico formal y producir el plan de implementación detallado (`blueprint`) para la ingesta en Telegraf y la actualización de los dashboards `SeismicMonitor` y `Health`.

---

## 📂 Estructura del Repositorio Implementada

```text
RSA-Intern-TIG-MQTT/
├── docs/
│   ├── analysis/
│   │   ├── 2026-09-02_diagnostico_ingesta_telemetria_status_acquisition.md
│   │   └── 2026-09-09_diagnostico_modelo_alertas_visualizacion_grafana.md  # [NUEVO/ACTUALIZADO] Diagnóstico técnico consolidado
│   ├── blueprints/
│   │   └── 2026-09-10_plan_implementacion_alertas_visualizacion_grafana.md # [NUEVO] Blueprint del Servidor TIG
│   └── progress/
│       ├── 2026-09-08_contexto-agente.md
│       └── 2026-09-10_contexto-agente.md                                  # [NUEVO] Documento de transición técnica
├── services/
│   ├── docker-unified/
│   │   ├── docker-compose.yml
│   │   └── telegraf.conf                                                  # [POR MODIFICAR] Ingesta de 3 topics especializados
│   └── grafana/
│       └── provisioning/
│           └── dashboards/
│               ├── health.json                                            # [POR MODIFICAR] Paneles para sensor, Drive y Ring Buffer
│               └── seismic_monitor.json                                   # [POR MODIFICAR] Tabla 3 columnas con diagnóstico único
```

---

## ⚙️ Decisiones Técnicas y Arquitectura Consolidada

### 1. Modelo Jerárquico de Estados y Remediabilidad Operativa
* **Rojo (Pérdida/Corrupción Irremediable de Datos)**:
  - `Offline`: Desconexión total de red o pérdida de nodo (LWT).
  - `Adquisicion`: Ring Buffer estancado (`stale_data`, $> 300\text{ s}$) o sin datos. *Remediable remotamente* reiniciando servicio o reseteando dsPIC.
  - `Sensor`: Aceleraciones triaxiales anómalas en reposo ($X, Y \not\approx 0$ o $Z \not\approx 9.81\text{ m/s}^2$) o falla de reloj. *No remediable remotamente*; acción defensiva: detener adquisición para no llenar disco con basura ni contaminar el correlador central.
  - `Disco`: Espacio libre crítico ($< 5\%$).
* **Amarillo (Atención Requerida sin Pérdida Inmediata)**:
  - `Drive`: Archivos `.mseed` protegidos por error de subida o acumulación de pendientes.
  - `Hardware`: Temperatura CPU $> 70^\circ\text{C}$ o subvoltaje/throttled.
  - `Disco`: Almacenamiento libre bajo ($5\%$ a $15\%$).
* **Verde (Nominal)**:
  - `OK`: Todos los subsistemas operando en parámetros óptimos.

### 2. Diseño Minimalista de `SeismicMonitor` (Monitor 24/7)
* Se eliminó la columna redundante de estado operativo. La tabla queda en **3 columnas**:
  `Estación` | `Conectividad` (`online`/`offline`) | `Diagnóstico Principal`.
* La columna **`Diagnóstico Principal`** muestra **exclusivamente una sola palabra** indicando el origen del problema (`OK`, `Offline`, `Adquisicion`, `Sensor`, `Drive`, `Disco`, `Hardware`).
* El fondo de la fila completa se colorea según el peor estado (`applyToRow: true`).
* Clic en la fila redirige dinámicamente al dashboard `Health` con la variable de la estación.

### 3. Enriquecimiento del Dashboard `Health` (`health.json`)
* **Google Drive**: Contadores de pendientes de subida (`pending_mseed`) y protegidos por fallo (`failed_uploads_protected`).
* **Integridad del Acelerómetro**: Tabla triaxial ($A_x, A_y, A_z$), fuente de reloj (`GPS`, `RPi`, `RTC`) y campo de error.
* **Salud de Adquisición**: Semáforo Ring Buffer y serie de tiempo de latencia `age_seconds`.

### 4. Ingesta Especializada en Telegraf (`telegraf.conf`)
* Suscripción a tres tópicos federados:
  - `rsa/seismic/smart/+/status/acquisition` $\rightarrow$ measurement `station_acquisition`.
  - `rsa/seismic/smart/+/status/sensor` $\rightarrow$ measurement `station_sensor`.
  - `rsa/seismic/smart/+/status/drive` $\rightarrow$ measurement `station_drive`.

---

## 🛠️ Artefactos y Documentación Generada

1. **Diagnóstico Técnico**: [`docs/analysis/2026-09-09_diagnostico_modelo_alertas_visualizacion_grafana.md`](../analysis/2026-09-09_diagnostico_modelo_alertas_visualizacion_grafana.md)
   - Contiene la fundamentación operativa, taxonomía de fallos y matriz de remediabilidad.
2. **Plan de Implementación Servidor TIG**: [`docs/blueprints/2026-09-10_plan_implementacion_alertas_visualizacion_grafana.md`](../blueprints/2026-09-10_plan_implementacion_alertas_visualizacion_grafana.md)
   - Especifica en 4 fases las configuraciones de Telegraf, consulta Flux unificada, paneles de Grafana y checkpoints con inyección MQTT sintética.

---

## 📋 Pasos Sugeridos para el Siguiente Agente

1. **Ejecutar Fase 1 del Blueprint en el Servidor TIG**:
   - Editar `services/docker-unified/telegraf.conf` agregando los tres bloques de `inputs.mqtt_consumer`.
   - Reiniciar Telegraf (`docker compose restart telegraf`) y validar logs limpios.
2. **Ejecutar Fase 2 del Blueprint en `SeismicMonitor`**:
   - Actualizar `seismic_monitor.json` con la consulta Flux de unión jerárquica y configurar overrides para la tabla de 3 columnas.
3. **Ejecutar Fase 3 del Blueprint en `Health`**:
   - Añadir los paneles de Drive, Sensor y Adquisición en `health.json` y subir la versión del dashboard.
4. **Validar con Pruebas Sintéticas (Fase 4)**:
   - Inyectar payloads vía `mosquitto_pub` y verificar transiciones de color en el navegador.
