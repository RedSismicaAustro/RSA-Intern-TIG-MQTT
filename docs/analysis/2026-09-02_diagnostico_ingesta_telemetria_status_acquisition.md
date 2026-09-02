---
proyecto: RSA-Intern-TIG-MQTT
tipo: diagnostico_tecnico
resolucion: pendiente
temas: [mqtt, telegraf, influxdb, grafana, telemetria, adquisicion, watchdog]
fecha: 2026-09-02
---

# Diagnóstico Técnico: Ingesta, Persistencia y Alertamiento de la Telemetría `status/acquisition` en el Stack TIG

**Fecha**: 2026-09-02  
**Proyecto / Repositorio**: `RSA-Intern-TIG-MQTT` (Servidor Central)  
**Componente(s) afectado(s)**: `telegraf` (`telegraf.conf`), `influxdb` (bucket telemetría), `grafana` (dashboards operativos y alertas)  
**Estado**: Diagnosticado (pendiente de implementación en servidor TIG)  
**Severidad**: Media (Mejora de observabilidad e inmunización operativa de la red)  

---

## 1. Resumen Ejecutivo

Como parte de la culminación del **Plan de Resiliencia del Pipeline de Adquisición** ([ADR-018](../../../../../rsa/RSA-Metodologias/decisiones/018_resiliencia_pipeline_adquisicion_acelerografo.md)) en las estaciones acelerográficas (`RSA-Acelerografo`), se implementó y validó en hardware el módulo `AcquisitionWatchdog`. Este componente audita continuamente el Ring Buffer en disco y publica cada 60 segundos el estado de frescura y latencia de adquisición en el tópico MQTT federado `rsa/seismic/smart/{station_id}/status/acquisition`.

Actualmente, el **Stack Central TIG** (Telegraf + InfluxDB + Grafana) solo consume los tópicos de salud de hardware (`telemetry/health`) y de detecciones sísmicas (`events/detected`). Al no existir una regla de suscripción ni un parser JSON para `status/acquisition` en la configuración de Telegraf, los mensajes publicados por las estaciones son ignorados por el servidor central. 

El presente diagnóstico documenta formalmente la interfaz de datos emitida por las estaciones de campo, el estado actual de la infraestructura central y el plan de trabajo requerido para ingerir, persistir y visualizar esta telemetría, habilitando un **semáforo de salud de adquisición en tiempo real** y alertas tempranas ante estancamientos en cualquier estación de la red sísmica.

---

## 2. Estado Actual

| Componente | Estado | Observaciones |
|---|---|---|
| **Acelerógrafos (`acelerografo-DEV00`)** | ✅ Operativo | Módulo `AcquisitionWatchdog` activo. Emite cada 60 s métricas de frescura (`age_seconds`, `status`) vía MQTT QoS 1. Validado en estación de pruebas. |
| **Broker MQTT Central** | ✅ Operativo | Recibe publicaciones en `rsa/seismic/smart/+/status/acquisition`. |
| **Telegraf (`telegraf.conf`)** | ⚠️ Desactualizado | No está suscrito al tópico `status/acquisition`. No procesa ni reenvía estos datos a InfluxDB. |
| **InfluxDB v2** | ⚠️ Sin Medición | No existe measurement ni esquema para almacenar la serie temporal de salud de adquisición. |
| **Grafana** | ⚠️ Sin Panel | No dispone de visualización de latencia ni semáforo de adquisición por estación. |
| **Sistema de Alertas** | ❌ Inexistente | No hay notificaciones automáticas cuando una estación entra en estado `warning: stale_data` ($> 300\text{ s}$). |

---

## 3. Evidencia y Especificación de la Telemetría de Origen

### 3.1. Interfaz de Publicación del Acelerógrafo (`montajes/acelerografo-DEV00`)

* **Módulo Emisor**: [`scripts/operation/mqtt/acquisition_watchdog.py`](file:///home/rsa/git/montajes/acelerografo-DEV00/scripts/operation/mqtt/acquisition_watchdog.py) / [`scripts/operation/mqtt/mqtt_coordinator.py`](file:///home/rsa/git/montajes/acelerografo-DEV00/scripts/operation/mqtt/mqtt_coordinator.py)
* **Tópico MQTT**: `rsa/seismic/smart/{station_id}/status/acquisition`
  - Ejemplo: `rsa/seismic/smart/DEV0/status/acquisition`, `rsa/seismic/smart/CHA01/status/acquisition`.
* **QoS**: `1`
* **Retain**: `false`
* **Periodicidad**: Cada `60 segundos` (temporizador síncrono en bucle principal).
* **Consulta Bajo Demanda**: Soportada vía comando MQTT `rsa/seismic/smart/{station_id}/cmd/get_acquisition_status`.

### 3.2. Esquemas de Payload JSON Emitidos

#### A. Estado Nominal (`status: "ok"`)
Emitido cuando la última trama del Ring Buffer tiene una antigüedad $\le 300\text{ segundos}$ respecto al reloj UTC del sistema:

```json
{
  "status": "ok",
  "last_frame_utc": "2026-09-02T21:51:09Z",
  "age_seconds": 1.6,
  "station_id": "DEV0",
  "timestamp": "2026-09-02T21:51:10Z"
}
```

#### B. Estado de Alerta / Datos Estancados (`status: "warning"`, `reason: "stale_data"`)
Emitido cuando la adquisición en C se detuvo, el bus SPI se desfasó o no ingresan nuevas tramas por más de 5 minutos:

```json
{
  "status": "warning",
  "reason": "stale_data",
  "last_frame_utc": "2026-08-27T19:46:03Z",
  "age_seconds": 432000.0,
  "threshold_seconds": 300,
  "station_id": "DEV0",
  "timestamp": "2026-09-01T10:48:00Z"
}
```

#### C. Estado de Error (`status: "error"`)
Emitido si el directorio `/home/rsa/data/ring-buffer/` no existe o no contiene archivos `.bin`:

```json
{
  "status": "error",
  "reason": "no_data_available",
  "station_id": "DEV0",
  "timestamp": "2026-09-02T21:51:10Z"
}
```

### 3.3. Evidencia de Validación de Campo en Estación de Pruebas
Captura directa del log de producción y broker MQTT registrada el `2026-09-02`:

```text
2026-09-02 21:45:10 - DEV0_mqtt_coordinator.log - INFO - [ACQUISITION_OK] Adquisición nominal: age=1.2s
2026-09-02 21:45:10 - DEV0_mqtt_coordinator.log - INFO - [MQTT_CONNECT] 174.138.41.251 | status=ok
```

---

## 4. Hallazgos y Análisis de Causa Raíz

### Hallazgo 1: Brecha de Observabilidad en la Red Central
* **Descripción**: Aunque las estaciones emiten activamente su estado de adquisición, el operador central en Grafana carece de visibilidad sobre si los acelerógrafos están adquiriendo datos en tiempo real o si sufrieron un bloqueo de hardware/SPI (como ocurrió en el incidente de CHA01).
* **Causa**: Telegraf no incluye la entrada `topics = ["rsa/seismic/smart/+/status/acquisition"]` en su bloque `inputs.mqtt_consumer`.

### Hallazgo 2: Tipado y Normalización de Métricas para InfluxDB
* **Descripción**: Los payloads contienen campos numéricos (`age_seconds`, `threshold_seconds`) y campos de cadena/estado (`status`, `reason`, `station_id`, `last_frame_utc`).
* **Causa**: Para permitir consultas eficientes en Flux y alertas en Grafana, `station_id`, `status` y `reason` deben indexarse como **Tags**, mientras que `age_seconds` debe almacenarse como un **Field** numérico (float).

---

## 5. Evaluación de Riesgo

| # | Escenario | Probabilidad | Impacto | Mitigación Requerida |
|---|---|---|---|---|
| **R1** | Parada silenciosa de adquisición en un nodo de campo sin detección inmediata por el personal técnico. | Alta | Crítico | Ingesta de `status/acquisition` en Telegraf y regla de alerta en Grafana. |
| **R2** | Desbordamiento de puntos en InfluxDB por alta frecuencia de reporte. | Baja | Bajo | Cada estación emite 1 punto por minuto (6 estaciones = 6 pts/min = ~8.640 pts/día), lo cual representa un consumo despreciable de almacenamiento y CPU. |

---

## 6. Opciones de Diseño para el Stack TIG

### Decisión 1: Integración del Consumidor en Telegraf

| Opción | Descripción | Ventaja | Desventaja |
|---|---|---|---|
| **Opción A (Extender `mqtt_consumer` existente)** | Añadir el tópico al bloque general de MQTT en `telegraf.conf`. | Menos bloques de configuración. | Complejidad al mezclar esquemas de métricas de hardware (`telemetry/health`) con adquisición (`status/acquisition`). |
| **Opción B (Bloque `inputs.mqtt_consumer` dedicado - Recomendada)** | Crear un bloque `[[inputs.mqtt_consumer]]` específico con `name_override = "station_acquisition"` y parsing JSON explícito. | Aislamiento claro del measurement, definición limpia de tags/fields y tags de estado deterministas. | Archivo de configuración ligeramente más largo. |

> **Recomendación**: Implementar la **Opción B** en `telegraf.conf` bajo el contenedor `rsa-telegraf`.

---

## 7. Mitigaciones Aplicadas

* **En Acelerógrafos**: ✅ Módulo `AcquisitionWatchdog` implementado, probado unitariamente (5/5 tests) y desplegado con éxito en el acelerógrafo de desarrollo.
* **En Servidor TIG**: *Ninguna aplicada aún — pendiente de implementación desde el entorno `montajes/server-ubuntu`.*

---

## 8. Backlog de Mejoras para el Stack TIG

1. **Configuración de Telegraf (`telegraf.conf`)**:
   - Agregar bloque consumidor MQTT para `rsa/seismic/smart/+/status/acquisition`.
   - Mapear `name_override = "station_acquisition"`.
   - Definir `tag_keys = ["station_id", "status", "reason"]` y `json_string_fields = ["last_frame_utc", "timestamp"]`.
2. **Reinicio y Verificación de Telegraf**:
   - `docker-compose restart telegraf` (o comando de gestión de servicios).
   - Verificar en logs de Telegraf la ingesta correcta de métricas hacia InfluxDB.
3. **Tablero de Control en Grafana**:
   - Crear panel tipo **State Timeline** o **Status Dot** mostrando el estado (`ok` = verde, `warning` = rojo/naranja) para todas las estaciones (`DEV0`, `CHA01`, etc.).
   - Crear gráfico de serie temporal con la curva de `age_seconds` (latencia en segundos).
4. **Reglas de Alerta Unificadas**:
   - Configurar regla de alerta en Grafana que evalúe si `age_seconds > 300` o `status != 'ok'` durante más de 3 minutos consecutivos.
   - Enrutamiento de alertas hacia Telegram o canal de monitoreo de la RSA.

---

## 9. Dependencias y Prerrequisitos

| Prerrequisito | Estado | Acción Requerida |
|---|---|---|
| Estaciones de campo emitiendo `status/acquisition` | ✅ Validado en DEV0 | Desplegar actualización en las demás estaciones de la flota. |
| Broker MQTT institucional accesible por Telegraf | ✅ Operativo | Sin cambios. |
| Acceso de edición a `docker-compose` y `telegraf.conf` en servidor Ubuntu | ⬜ Por abordar | Conectar al workspace `montajes/server-ubuntu` para aplicar los cambios. |

---

## 10. Plan de Validación Futuro

| # | Checkpoint | Criterio de Éxito |
|---|---|---|
| **CP-1** | Ingesta en Telegraf | `docker logs rsa-telegraf` sin errores de parseo JSON al recibir mensajes de `status/acquisition`. |
| **CP-2** | Persistencia en InfluxDB | Consulta Flux `from(bucket: "telegraf") |> range(start: -15m) |> filter(fn: (r) => r._measurement == "station_acquisition")` retorna registros con `age_seconds` y tags de estación. |
| **CP-3** | Visualización en Grafana | Dashboard muestra panel con semáforo verde para estaciones nominales y curva de latencia. |
| **CP-4** | Test de Alerta (Simulación) | Detener temporalmente adquisición en una estación (`registrocontinuo stop`); observar transición a `warning` en Grafana y disparo de la alerta en $\le 5$ minutos. |
