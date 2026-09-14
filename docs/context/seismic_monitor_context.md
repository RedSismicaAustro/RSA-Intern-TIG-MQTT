---
proyecto: RSA-Intern-TIG-MQTT
tipo: contexto_tecnico
archivo: services/grafana/provisioning/dashboards/seismic_monitor.json
temas: [grafana, dashboard, seismic-monitor, flux, alertas, jerarquia, matriz-salud]
generado: 2026-09-14
---
# seismic_monitor.json — Contexto para Agentes IA

> Dashboard principal de supervisión de red tipo matriz (Estación, Conectividad, Diagnóstico Principal) con motor de votación jerárquico Flux que clasifica y prioriza en tiempo real las anomalías de las estaciones acelerométricas con enlace directo al dashboard Health.

**Ruta**: `services/grafana/provisioning/dashboards/seismic_monitor.json`  
**LOC**: 248 | **Lenguaje/Formato**: JSON (Grafana Dashboard Model v39) | **Dependencias**: Grafana 11.2.0, InfluxDB v2 Datasource (`uid: P951FEA4DE68E13C5`), Bucket `telemetry`, Dashboard Health (`uid: ffcrjb8bumy2ob2`)  
**Proceso**: Provisionado automáticamente en el arranque de Grafana vía `services/grafana/provisioning/dashboards/dashboards.yaml`.

---

## 🎯 Arquitectura y Mecanismo de Votación Flux

El dashboard presenta una vista panorámica compacta y limpia de la red mediante una tabla de 3 columnas (`Estación`, `Conectividad`, `Diagnóstico Principal`). Para evitar alertas ambiguas o confusas, implementa un **motor de votación jerárquica** en lenguaje Flux que recopila métricas de 7 subsistemas independientes en una ventana móvil de 7 días, asigna un peso de severidad numérico a cada estado anómalo, y selecciona mediante `sort() |> limit(n: 1)` el diagnóstico más crítico por estación.

```mermaid
graph TD
    subgraph InfluxDB Telemetry Bucket
        M1[rsa / state / status] --> V1[conn_vote: Offline (Peso 6)]
        M2[station_acquisition / age_seconds] --> V2[acq_vote: Adquisicion (Peso 5)]
        M3[station_sensor / az] --> V3[sensor_vote: Sensor (Peso 4)]
        M4[rsa / health / disk_percent] --> V4[disk_vote: Disco (Peso 3/2)]
        M5[station_drive / pending_mseed] --> V5[drive_vote: Drive (Peso 2)]
        M6[rsa / health / cpu_temp_c] --> V6[temp_vote: Temperatura (Peso 1)]
        M7[rsa / health / ram_percent] --> V7[ram_vote: Memoria (Peso 1)]
    end

    V1 & V2 & V3 & V4 & V5 & V6 & V7 --> U[union: Agrupación por station_id]
    U --> Sort[sort desc _value |> limit n:1]
    Sort --> Map[Mapeo a Diagnóstico y Conectividad]
    Map --> Grid[Panel Tabla: SeismicMonitor]
    Grid -->|Click en Fila / Celda| Link[Navegación a /d/ffcrjb8bumy2ob2/health?var-station=STATION]
```

### Escala de Precedencia y Severidad

| Nivel de Prioridad | Diagnóstico | Condición Evaluada en Flux | Color en Matriz |
|:------------------:|-------------|----------------------------|-----------------|
| **6 (Máxima)** | `Offline` | `status == "offline"` en telemetría de estado | Rojo (`dark-red`) |
| **5** | `Adquisicion` | `status == "error"` o `age_seconds > 300.0` en watchdog | Rojo (`dark-red`) |
| **4** | `Sensor` | `status == "error"` en comprobación triaxial | Rojo (`dark-red`) |
| **3 / 2** | `Disco` | `disk_percent > 95.0` (crítico, peso 3) o `> 90.0` (advertencia, peso 2) | Naranja (`dark-orange`) |
| **2** | `Drive` | `status == "warning"` o `pending_mseed > 3` | Amarillo (`semi-dark-yellow`) |
| **1** | `Temperatura` | `cpu_temp_c > 70.0` | Naranja (`dark-orange`) |
| **1** | `Memoria` | `ram_percent > 90.0` | Naranja (`dark-orange`) |
| **0 (Base)** | `OK` | Sin anomalías detectadas en ningún subsistema | Verde (`green`) |

*Nota sobre Throttled*: Tras calibración operativa, el indicador de throttled fue desvinculado de las alertas del monitor principal para evitar falsos positivos derivados de variaciones térmicas transitorias de las Raspberry Pi.

---

## ⚙️ Configuraciones y Parámetros del Dashboard

| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| `uid` | `ffcrjb8bumy2ob` | Identificador único del dashboard en Grafana. |
| `title` | `SeismicMonitor` | Título del dashboard. |
| `refresh` | `5s` | Refresco automático para monitoreo en pantalla operativa (kiosco). |
| `time.from` / `time.to` | `now-2d` a `now` | Rango temporal predeterminado. |
| Estaciones filtradas | `CHA1, CHA2, DEV0, FERR, TENG, TEST` | Expresión regular `r.station_id =~ /^(CHA1\|CHA2\|DEV0\|FERR\|TENG\|TEST)$/`. |
| Datasource UID | `P951FEA4DE68E13C5` | UID de la conexión a InfluxDB v2 en Grafana. |

---

## 🧩 Componentes y Opciones Visuales Clave

| Componente | Configuración | Comportamiento |
|------------|---------------|----------------|
| **Panel Tabla (`id: 8`)** | `type: "table"`, `gridPos: {h: 10, w: 24}` | Tabla de ancho completo de 24 columnas. |
| **Color de Fila Dinámico** | `cellOptions: { applyToRow: true, mode: "gradient", type: "color-background" }` | Aplica un suave degradado en toda la fila reflejando el color del Diagnóstico Principal. |
| **Data Link en Estación** | `/d/ffcrjb8bumy2ob2/health?from=now-2d&to=now&refresh=5s&var-station=${__data.fields["Estación"]}` | Redirige al dashboard Health preseleccionando la estación pulsada. |
| **Data Link en Diagnóstico** | Mismo target que columna Estación | Permite al operador hacer clic sobre el texto de diagnóstico para saltar al detalle. |
| **Transformación Organize** | `indexByName`: `Estación: 0`, `Conectividad: 1`, `Diagnóstico Principal: 2` | Garantiza el orden estricto de las 3 columnas sin campos intermedios residuales. |

---

## ⚠️ Limitaciones Conocidas / TODOs

- **Incorporación de Nuevas Estaciones**: Al desplegar un nuevo nodo acelerográfico, debe incluirse su código en la expresión regular de filtrado de estaciones de la consulta Flux.
- **Enmascaramiento por Jerarquía**: Si una estación experimenta simultáneamente una falla crítica de adquisición y una advertencia de Google Drive o disco, la matriz principal mostrará exclusivamente `Adquisicion` debido a su mayor peso (5 vs 2). El operador debe abrir el dashboard `Health` para inspeccionar el estado integral de todos los subsistemas.
