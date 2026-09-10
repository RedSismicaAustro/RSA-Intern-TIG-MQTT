---
proyecto: RSA-Intern-TIG-MQTT
tipo: diagnostico_tecnico
resolucion: en_proceso
temas: [grafana, visualizacion, alertas, telemetria, mqtt, telegraf, influxdb, acelerografo, gdrive, observabilidad]
fecha: 2026-09-09
---

# Diagnóstico Técnico: Modelo Jerárquico de Alertas, Visualización Centralizada en Grafana y Estrategia de Telemetría Eficiente en Estaciones

**Fecha**: 2026-09-09 (Actualizado: 2026-09-10)  
**Proyecto / Repositorio**: `RSA-Intern-TIG-MQTT` (Servidor Central) & `acelerografo-DEV00` (Software de Estaciones)  
**Componente(s) afectado(s)**: `grafana` (dashboards `SeismicMonitor` y `Health`), `telegraf` (`telegraf.conf`), `influxdb` (bucket `telemetry`), telemetría de campo en `acelerografo` (`mqtt_coordinator.py`, `gestor_archivos_acq.py`, `comprobar_registro`)  
**Estado**: En proceso (acuerdos consolidados, listo para blueprint de implementación)  
**Severidad**: Alta (Afecta directamente la observabilidad, la detección temprana de fallos físicos y la integridad de los datos sismológicos)  

---

## 1. Resumen Ejecutivo

La Red Sísmica del Austro (RSA) mantiene una estación de monitoreo central (PC de guardia 24/7) que proyecta permanentemente el dashboard **`SeismicMonitor`** de Grafana para auditar el estado de las 6 estaciones acelerográficas operativas (`CHA1`, `CHA2`, `DEV0`, `FERR`, `TENG`, `TEST`). Actualmente, este tablero opera bajo un esquema binario: **Verde (`online`)** vs. **Rojo (`offline`)**, con navegación interactiva mediante clic hacia el dashboard de detalle **`Health`**.

Este mecanismo binario presenta una **ceguera operativa crítica**: una estación puede figurar en verde (`online`) transmitiendo heartbeats regulares mientras internamente sufre fallos graves que conllevan la pérdida irremediable de datos sismológicos o la inyección de señales corruptas al sistema central, tales como:
1. **Congelamiento de la adquisición** (fallo en el binario C `registro_continuo` o desfasaje del bus SPI).
2. **Incoherencia física del sensor acelerométrico** (descalibración, daño electrónico o valores triaxiales anómalos).
3. **Fallas en la sincronización con Google Drive** (acumulación de archivos sin subir).

El presente diagnóstico consolida el **modelo jerárquico de alertas (Verde / Amarillo / Rojo)**, define la simplificación visual máxima de `SeismicMonitor` (3 columnas con **diagnóstico en una sola palabra** para lectura rápida a distancia), especifica el enriquecimiento analítico del dashboard `Health` (donde se desglosan todos los detalles técnicos), y establece la **unificación de cadencia en las estaciones a 5 minutos acoplada a `telemetry/health`**, optimizando el uso del canal MQTT.

---

## 2. Estado Actual

| Componente | Entorno | Estado | Observaciones |
|---|---|---|---|
| **Monitor de Guardia (`SeismicMonitor`)** | Servidor TIG | ⚠️ Parcialmente Ciego | Solo evalúa la métrica `state` (`online` / `offline`). Estaciones con adquisición detenida o sensor roto se muestran erróneamente en verde. |
| **Tablero de Detalle (`Health`)** | Servidor TIG | ⚠️ Incompleto | Muestra hardware (CPU, RAM, Disco, Temp, Throttled), pero carece de paneles de adquisición (Watchdog), estado de Google Drive e integridad del acelerómetro. |
| **Ingesta Telegraf (`telegraf.conf`)** | Servidor TIG | ⚠️ Desactualizado | No ingiere los tópicos especializados de adquisición (`status/acquisition`), sensor (`status/sensor`) ni Drive (`status/drive`). |
| **Watchdog de Adquisición** | Estaciones | ✅ Listo en DEV0 | Módulo `AcquisitionWatchdog` implementado en `acelerografo-DEV00`. Pendiente acoplar al ciclo unificado de 5 minutos y desplegar en la flota. |
| **Comprobación de Integridad Sensor** | Estaciones | ⚠️ Manual | Comando `comprobar` (`comprobar_registro`) operativo localmente pero sin automatización periódica de 5 min, validación de umbrales ni emisión MQTT. |
| **Gestión Google Drive** | Estaciones | ⚠️ Sin Reporte Central | `gestor_archivos_acq.py` protege archivos fallidos localmente (`esta_protegido()`), pero no reporta a la red central el conteo de archivos pendientes. |

---

## 3. Evidencia y Análisis de Criticidad Operativa

### 3.1. Diferenciación de Fallos Críticos (Remediabilidad Remota vs. Acción de Contención)

La comprobación de la **Salud de Adquisición** y la **Integridad del Acelerómetro** tienen la misma máxima severidad (ambas representan pérdida irreparable de datos). Sin embargo, su capacidad de resolución operativa difiere radicalmente:

```text
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                           MATRIZ DE REMEDIABILIDAD OPERATIVA                                    │
├─────────────────────────┬──────────────┬───────────────────────────────┬────────────────────────┤
│ Tipo de Fallo Crítico   │ Severidad    │ ¿Remediable Remotamente?      │ Acción Operativa       │
├─────────────────────────┼──────────────┼───────────────────────────────┼────────────────────────┤
│ Adquisición Detenida    │ ROJO CRÍTICO │ SÍ                            │ Reiniciar servicio C / │
│ (Ring Buffer congelado) │              │ (Comando SSH / systemd)       │ reset dsPIC vía MCLR   │
├─────────────────────────┼──────────────┼───────────────────────────────┼────────────────────────┤
│ Sensor Acelerométrico   │ ROJO CRÍTICO │ NO                            │ DETENER adquisición    │
│ Incoherente (Daño físico│              │ (Requiere visita técnica a la │ para no saturar disco  │
│ o descalibración grave) │              │ estación para reparar sensor) │ ni corromper eventos   │
└─────────────────────────┴──────────────┴───────────────────────────────┴────────────────────────┘
```

* **Adquisición Congelada**: Puede mitigarse de inmediato mediante comandos remotos (`sudo systemctl restart rsa-acelerografo` o script de rescate).
* **Sensor Dañado**: Ningún reinicio remoto puede reparar un acelerómetro roto o con deriva destructiva. En este escenario, lo máximo que el operador o el sistema autónomo puede y debe hacer de forma remota es **detener la adquisición continua** para:
  1. Evitar llenar el almacenamiento de archivos con ruido inservible.
  2. Evitar disparos falsos de detección GPD/STA-LTA que induzcan errores espurios en el Correlador Regional Central.

---

### 3.2. Taxonomía de Estados por Color (Semáforo de Criticidad)

```text
┌───────────────────────────────────────────────────────────────────────────────────────┐
│                               TAXONOMÍA DE ALERTAS RSA                                │
├────────────────────────┬──────────────────────────────────────────────────────────────┤
│ ROJO (CRÍTICO)         │ Pérdida o corrupción IRREMEDIABLE de datos sismológicos      │
├────────────────────────┼──────────────────────────────────────────────────────────────┤
│ AMARILLO (ADVERTENCIA) │ Anomalía que requiere ATENCIÓN pero NO pierde datos          │
├────────────────────────┼──────────────────────────────────────────────────────────────┤
│ VERDE (NOMINAL)        │ Operación íntegra de adquisición, hardware y sincronización  │
└────────────────────────┴──────────────────────────────────────────────────────────────┘
```

#### Eventos ROJOS (Críticos - Pérdida / Corrupción de Datos):
1. **Desconexión Total (`offline`)**: Pérdida de enlace LWT MQTT, corte de energía o caída total del nodo.
2. **Adquisición Estancada (`stale_data` / `no_data_available`)**: Antigüedad de tramas en Ring Buffer $> 300\text{ s}$ o ausencia de datos en disco.
3. **Incoherencia del Sensor ($A_x, A_y, A_z$ fuera de rango)**: Aceleraciones en reposo desviadas de los valores físicos nominales ($X \approx 0$, $Y \approx 0$, $Z \approx 9.81\text{ m/s}^2$) o falla grave en la fuente de reloj.
4. **Espacio en Disco Crítico ($< 5\%$)**: Peligro inminente de parada forzada del sistema de archivos o montura en modo sólo lectura.

#### Eventos AMARILLOS (Advertencia - Atención Requerida sin Pérdida Inmediata):
1. **Fallo en Sincronización Google Drive (`drive_upload_failed`)**: Archivos `.mseed` protegidos por error de subida o acumulación de archivos pendientes $> 3$. Los datos están a salvo en la tarjeta de almacenamiento local gracias a `esta_protegido()`.
2. **Estrés Térmico o Eléctrico**: Temperatura de CPU $> 70^\circ\text{C}$ o alerta de subvoltaje/throttling (`throttled != "0x0"`).
3. **Espacio en Disco Bajo**: Almacenamiento libre entre $5\%$ y $15\%$.

#### Eventos VERDES (Nominales):
1. Conexión online activa, adquisición al día ($\text{latencia} \le 60\text{ s}$), sensor dentro de tolerancias nominales, subidas a Drive al día y parámetros de hardware saludables.

---

## 4. Decisiones de Diseño e Implementación

### Decisión 1: Arquitectura de Agregación de Salud (Servidor Central TIG)

Se adopta la **Opción B (Cálculo Server-Side en Grafana/Flux)**:
* Las estaciones publican sus métricas especializadas en tópicos MQTT independientes hacia el broker.
* Telegraf ingiere los datos en measurements limpios de InfluxDB (`rsa`, `station_acquisition`, `station_sensor`, `station_drive`).
* Grafana ejecuta una consulta Flux consolidada en `SeismicMonitor` que calcula el estado de severidad máxima:
  $$\text{Estado Fila} = \text{peor\_estado}(\text{Conectividad}, \text{Adquisición}, \text{Sensor}, \text{Drive}, \text{Disco})$$
* **Ventaja**: El servidor maneja de forma natural la desconexión total (si una estación cae, el LWT `offline` se impone inmediatamente en Rojo, sin depender de que la estación envíe nada).

---

### Decisión 2: Diseño Minimalista de `SeismicMonitor` (Diagnóstico de Una Sola Palabra)

Para maximizar la claridad en el monitor 24/7 y permitir identificar el origen del problema de un vistazo desde la distancia, la columna de diagnóstico muestra **únicamente una palabra** indicando la ubicación del fallo. Los detalles numéricos y descriptivos se consultan al hacer clic y abrir `Health`.

```text
+-----------+---------------+-----------------------+---------------------+
| Estación  | Conectividad  | Diagnóstico Principal | Color de Fila       |
+-----------+---------------+-----------------------+---------------------+
| CHA1      | online        | OK                    | Verde               |
| CHA2      | online        | Drive                 | Amarillo            |
| DEV0      | online        | Adquisicion           | Rojo                |
| FERR      | online        | Sensor                | Rojo                |
| TENG      | offline       | Offline               | Rojo                |
| TEST      | online        | OK                    | Verde               |
+-----------+---------------+-----------------------+---------------------+
```

#### Catálogo Cerrado de Diagnósticos en `SeismicMonitor`:
- **`OK`**: Todos los sistemas nominales (Verde).
- **`Offline`**: Desconexión total de red/LWT (Rojo).
- **`Adquisicion`**: Ring Buffer congelado o sin datos de adquisición (Rojo).
- **`Sensor`**: Lecturas triaxiales anómalas o fallo de reloj en el acelerómetro (Rojo).
- **`Drive`**: Archivos `.mseed` protegidos o pendientes de subir a la nube (Amarillo).
- **`Disco`**: Almacenamiento libre $< 15\%$ (Amarillo) o $< 5\%$ (Rojo).
- **`Hardware`**: Temperatura $> 70^\circ\text{C}$ o subvoltaje/throttled (Amarillo).

1. **Regla de Color de Fila (`applyToRow: true`)**:
   - **Rojo (`dark-red`)**: Conectividad = `offline` O diagnóstico $\in \{\text{Offline, Adquisicion, Sensor, Disco (<5\%)}\}$.
   - **Amarillo (`dark-orange` / `yellow`)**: Conectividad = `online` Y diagnóstico $\in \{\text{Drive, Hardware, Disco (5-15\%)}\}$.
   - **Verde (`green`)**: Conectividad = `online` Y diagnóstico = `OK`.
2. **Interacción Click-Through**:
   - Al hacer clic en cualquier celda de la fila, el navegador redirige a `Health` con `var-station=${__data.fields["Estación"]}` para auditar los detalles numéricos.

---

### Decisión 3: Enriquecimiento del Dashboard de Detalle `Health` (`health.json`)

Al hacer clic en una estación con advertencia o error, el operador accede al desglose completo mediante tres nuevas secciones estructuradas:

#### A. Sección Google Drive (Sincronización Cloud)
* **Panel Stat / Contador**: `Archivos Pendientes de Subida` (cantidad de archivos `.mseed` retenidos localmente a la espera de subir).
* **Panel Stat / Alerta**: `Archivos Protegidos por Fallo` (archivos retenidos por error en `drive_status.json`).
* **Tabla de Última Subida**: Timestamp de la última sincronización exitosa, espacio libre y motivo de advertencia en caso de existir.

#### B. Sección Integridad del Acelerómetro (Sensor Físico)
* **Tabla de Diagnóstico Triaxial y Reloj**:
  - Lecturas en reposo: $A_x$ ($\text{m/s}^2$), $A_y$ ($\text{m/s}^2$), $A_z$ ($\text{m/s}^2$).
  - Fuente de Reloj activa: `GPS`, `RPi`, `RTC`.
  - Error de Reloj / Sensor: Campo de texto con el detalle de error (`null` si nominal, o extracto del tipo `E3/GPS: No se pudo comprobar...`, `accelerometer_anomaly`).
* **Indicador de Calibración**: Verde si $|X| \le 0.5$, $|Y| \le 0.5$ y $|Z - 9.81| \le 0.8$; Rojo en caso de desvío.

#### C. Sección Salud de Adquisición (Pipeline Local)
* **Panel Semáforo Ring Buffer**: Indicador de estado (`ok` verde, `warning` amarillo, `error` rojo).
* **Gráfica de Latencia de Adquisición (`Time Series`)**: Serie temporal de `age_seconds` con línea de umbral en 300 s.
* **Timestamp Última Trama Adquirida**: `last_frame_utc` auditado en disco.

---

### Decisión 4: Cadencia Unificada a 5 Minutos Acoplada a `telemetry/health`

Para evitar dispersión de temporizadores y ráfagas innecesarias en la red móvil o satelital, **la evaluación de Adquisición y Sensor se unifica cada 5 minutos (300 segundos)**, acoplada directamente al ciclo habitual de telemetría de salud de `mqtt_coordinator.py`:

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│               CADENCIA UNIFICADA DE EVALUACIÓN Y EMISIÓN MQTT EN CAMPO                 │
├─────────────────────────┬───────────────────────────┬──────────────────────────────────┤
│ Subsistema              │ Periodicidad de Evaluación│ Comportamiento de Emisión        │
├─────────────────────────┼───────────────────────────┼──────────────────────────────────┤
│ Hardware (CPU, RAM, T°) │ Cada 5 minutos (300 s)    │ telemetry/health                 │
│ Adquisición (Watchdog)  │ Cada 5 minutos (300 s)    │ status/acquisition (QoS 1, retain│
│ Sensor (Acelerómetro)   │ Cada 5 minutos (300 s)    │ status/sensor (QoS 1, retain)    │
│ Google Drive            │ Cada 1 hora (post-subida) │ status/drive (QoS 1, retain)     │
└─────────────────────────┴───────────────────────────┴──────────────────────────────────┘
```

1. **Acoplamiento en `mqtt_coordinator.py`**:
   - Cada 300 segundos, el bucle principal de telemetría evalúa en memoria:
     1. Métricas de hardware del sistema (`telemetry/health`).
     2. Módulo `AcquisitionWatchdog` sobre el Ring Buffer $\rightarrow$ emite a `status/acquisition`.
     3. Wrapper `comprobar_registro` sobre el acelerómetro $\rightarrow$ emite a `status/sensor`.
2. **Disparo Inmediato ante Detección de Error**:
   - Si la adquisición o el sensor arrojan un error durante el ciclo de evaluación, se emite inmediatamente con flag `retain = true` para que el broker mantenga persistente el estado de alerta hasta que sea restaurado.
   - Si una estación se recupera, la siguiente evaluación de 5 minutos publica automáticamente el estado nominal (`status: "ok"`), limpiando la alarma en Grafana.

---

## 5. Especificación de Contratos de Telemetría MQTT

### 1. Salud de Adquisición (Cada 5 minutos)
* **Tópico**: `rsa/seismic/smart/{station_id}/status/acquisition`
* **QoS**: `1` | **Retain**: `true`
* **Payload Nominal**:
  ```json
  {
    "status": "ok",
    "age_seconds": 1.4,
    "last_frame_utc": "2026-09-10T15:00:00Z",
    "reason": "nominal",
    "station_id": "DEV0",
    "timestamp": "2026-09-10T15:00:01Z"
  }
  ```
* **Payload en Error**: `status: "error"`, `reason: "stale_data"`, `age_seconds: 360.0`.

### 2. Integridad del Sensor Acelerométrico (Cada 5 minutos)
* **Tópico**: `rsa/seismic/smart/{station_id}/status/sensor`
* **QoS**: `1` | **Retain**: `true`
* **Payload Nominal**:
  ```json
  {
    "status": "ok",
    "ax": 0.0037,
    "ay": -0.0014,
    "az": 9.8014,
    "clock_source": "GPS",
    "clock_error": null,
    "reason": "nominal",
    "station_id": "DEV0",
    "timestamp": "2026-09-10T15:00:02Z"
  }
  ```
* **Payload en Error**: `status: "error"`, `reason: "accelerometer_anomaly"`, `az: 0.00` o `clock_error: "E3/GPS"`.

### 3. Sincronización Google Drive (Cada 1 hora tras ronda de subidas)
* **Tópico**: `rsa/seismic/smart/{station_id}/status/drive`
* **QoS**: `1` | **Retain**: `true`
* **Payload Nominal**:
  ```json
  {
    "status": "ok",
    "pending_mseed": 0,
    "failed_uploads_protected": 0,
    "free_disk_percent": 45.2,
    "last_upload_utc": "2026-09-10T14:02:15Z",
    "reason": "all_synced",
    "station_id": "DEV0",
    "timestamp": "2026-09-10T15:02:00Z"
  }
  ```
* **Payload en Advertencia**: `status: "warning"`, `pending_mseed: 4`, `failed_uploads_protected: 2`, `reason: "upload_retry_retained"`.

---

## 6. Backlog de Implementación Segmentado

### A. Tareas en el Servidor Central TIG (`RSA-Intern-TIG-MQTT`)
1. **Configuración de Telegraf (`telegraf.conf`)**:
   - Añadir bloques de consumo para los tres tópicos especializados:
     - `name_override = "station_acquisition"` con tags `[station_id, status, reason]` y field `age_seconds`.
     - `name_override = "station_sensor"` con tags `[station_id, status, clock_source]` y fields `[ax, ay, az, clock_error]`.
     - `name_override = "station_drive"` con tags `[station_id, status, reason]` y fields `[pending_mseed, failed_uploads_protected, free_disk_percent]`.
2. **Dashboard `SeismicMonitor` (`seismic_monitor.json`)**:
   - Reescribir la consulta Flux para cruzar `state`, `station_acquisition`, `station_sensor` y `station_drive`.
   - Modificar la estructura de tabla a 3 columnas: `Estación`, `Conectividad`, `Diagnóstico Principal` (con una sola palabra: `OK`, `Offline`, `Adquisicion`, `Sensor`, `Drive`, `Disco`, `Hardware`).
   - Configurar los overrides de color de fila completa (`dark-red`, `yellow`, `green`).
3. **Dashboard `Health` (`health.json`)**:
   - Crear la fila de paneles para **Google Drive**: contadores de pendientes y protegidos.
   - Crear la fila de paneles para **Integridad del Acelerómetro**: tabla con $A_x, A_y, A_z$, fuente de reloj y errores.
   - Crear los paneles de **Salud de Adquisición**: curva de latencia `age_seconds` y semáforo Ring Buffer.

### B. Tareas en las Estaciones Acelerográficas (`acelerografo-DEV00`)
1. **Módulo de Adquisición (`mqtt_coordinator.py` / `AcquisitionWatchdog`)**:
   - Acoplar la evaluación de adquisición al ciclo de 5 minutos de `telemetry/health` emitiendo con QoS 1 y `retain = true`.
2. **Módulo de Comprobación de Sensor (`comprobar_registro`)**:
   - Integrar la invocación periódica de `comprobar_registro` cada 5 minutos dentro de `mqtt_coordinator.py`.
   - Evaluar tolerancias ($X, Y \approx 0, Z \approx 9.81$) y publicar en `status/sensor`.
   - Incorporar comando de contingencia: si el sensor falla de forma continua, opción de suspender adquisición para no contaminar el correlador central.
3. **Instrumentación de Subidas a Drive (`gestor_archivos_acq.py`)**:
   - Integrar la publicación de `status/drive` al finalizar cada ronda de subida horaria.

---

## 7. Plan de Validación

| # | Checkpoint | Criterio de Éxito |
|---|---|---|
| **CP-1** | Ingesta Telegraf | Telegraf ingiere los tres measurements en InfluxDB sin errores de tipos o desbordamientos. |
| **CP-2** | Visualización Minimalista en `SeismicMonitor` | Fila cambia a **Rojo** con diagnóstico `Adquisicion` si `age_seconds > 300`, `Sensor` si acelerómetro falla, u `Offline` si desconecta; cambia a **Amarillo** con diagnóstico `Drive` ante pendientes; muestra `OK` en **Verde** en estado nominal. |
| **CP-3** | Inspección en `Health` | Clic en fila abre `Health` mostrando la tabla de aceleraciones ($X, Y, Z$), el reloj, el estado de Drive y la curva de latencia. |
| **CP-4** | Eficiencia y Sincronía en 5 Minutos | Confirmar mediante `mosquitto_sub` que las estaciones publican sincronizadas cada 5 minutos junto a `telemetry/health`, sin ráfagas intermedias. |
