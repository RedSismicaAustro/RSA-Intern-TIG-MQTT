---
id: ADR-019
titulo: Modelo Jerárquico de Alertas y Visualización Centralizada de Estaciones en Grafana
estado: Aceptado
fecha: 2026-09-14
temas: [grafana, flux, alertas, jerarquia, dashboards, health, seismic-monitor, mqtt, telemetria, testing]
entorno: RSA-Intern-TIG-MQTT
---

# ADR-019: Modelo Jerárquico de Alertas y Visualización Centralizada de Estaciones en Grafana

## Estado

**Aceptado** | Fecha: 2026-09-14

---

## Contexto

Con la integración de nuevas telemetrías especializadas en la Red Sísmica del Austro (vigilancia de adquisición en Ring Buffer, comprobación física triaxial del sensor y sincronización de Google Drive), el monitoreo centralizado en Grafana enfrentaba varios problemas críticos:

1. **Ambigüedad y Confusión Diagnóstica**: En versiones anteriores, estados heterogéneos de hardware se agrupaban bajo una etiqueta genérica ("Hardware"), impidiendo discernir a primera vista si la anomalía se debía a temperatura, espacio en disco, memoria o estrangulamiento térmico.
2. **Conflicto y Ausencia de Jerarquía en Alertas**: Cuando una estación presentaba anomalías concurrentes (ej. retención de archivos en Google Drive y pérdida del flujo de adquisición sísmica), no existía una regla determinista de precedencia; alertas de menor severidad competían o enmascaraban fallos críticos del flujo sismológico.
3. **Falsos Positivos y Fatiga de Alertas por Throttling**: El parámetro `throttled` de las Raspberry Pi emitía alertas rojas continuas por variaciones transitorias de voltaje o picos breves de temperatura normales en gabinetes de campo, generando fatiga operativa.
4. **Sobrecarga Cognitiva y Rendimiento en Grafana**: El despliegue simultáneo de 18 paneles para múltiples estaciones en el dashboard detallado provocaba saturación visual ("apretujamiento de información") y sobrecarga innecesaria de consultas periódicas sobre InfluxDB.
5. **Dificultad de Validación Aislada en Pruebas**: Los tests de integración sufrían de traslapes en el broker MQTT debido a que los tópicos de prueba (ej. estación `TEST`) retenían datos de error de sesiones o equipos previos que contaminaban la evaluación de nuevos escenarios.

---

## Opciones Evaluadas

### Opción A: Motor Nativo de Alertas de Grafana (Grafana Unified Alerting)
Configurar reglas de alerta independientes por cada métrica mediante el motor de alertas de Grafana.
- **Ventajas**: Integración directa con canales de notificación push (Telegram, Email, Webhooks).
- **Desventajas**: No resuelve la necesidad de una matriz de supervisión compacta para pantallas operativas (kiosco); no permite consolidar una columna única de "Diagnóstico Principal" calculada dinámicamente por fila; introduce alta complejidad para modelar precedencias y dependencias entre múltiples alertas concurrentes en una misma celda.

### Opción B: Daemon de Pre-procesamiento de Estado en el Servidor (Consumidor MQTT Intermedio)
Implementar un microservicio en Python dentro del stack Docker que procese la telemetría, calcule la jerarquía de salud y republique un tópico sintético `status/overall`.
- **Ventajas**: Grafana realiza consultas simples sobre un único campo pre-calculado.
- **Desventajas**: Añade un punto único de fallo (SPOF) adicional en la arquitectura; introduce latencia de procesamiento adicional; genera duplicidad de lógica de cálculo entre el daemon e InfluxDB; incrementa el costo de mantenimiento de contenedores Docker.

### Opción C: Votación Jerárquica en Consultas Flux, Filas Colapsables en Health e Inyector Sintético Aislado (Elegida)
Consolidar la jerarquía directamente en consultas analíticas Flux de InfluxDB v2, organizar la vista detallada en filas colapsables temáticas y crear un arnés de pruebas sintéticas de 5 canales.
- **Ventajas**:
  - Elimina intermediarios: la lógica reside en el motor analítico de InfluxDB y se provisiona junto al dashboard en código fuente JSON.
  - Escala de severidad determinista: resuelve conflictos seleccionando con precisión matemática el diagnóstico de mayor peso.
  - Cero falsos positivos por throttling térmico habitual al convertirlo en un dato puramente informativo.
  - Reducción drástica del estrés visual y de consultas concurrentes mediante filas colapsables por defecto.
  - Garantía de aislamiento determinista en pruebas de integración mediante publicación simultánea de 4 canales nominales + 1 canal de prueba.
- **Desventajas**:
  - Requiere mantener sincronizada la lista de estaciones en el regex de la consulta Flux en caso de desplegar nuevas estaciones.
  - Limitación de deep-linking en Grafana v11: las URLs hacia paneles anidados dentro de filas colapsadas no abren automáticamente la fila, requiriendo que el operador la expanda manualmente.

---

## Decisión

Se eligió la **Opción C** mediante cuatro implementaciones arquitectónicas coordinadas:

### 1. Motor de Votación Jerárquico en Flux (`seismic_monitor.json`)
Se estructuró una consulta Flux en el panel principal tipo tabla con una matriz de 3 columnas (`Estación`, `Conectividad`, `Diagnóstico Principal`). La consulta evalúa 7 flujos de métricas en paralelo y asigna una escala de pesos de severidad decreciente:

$$\text{Offline (6)} > \text{Adquisición (5)} > \text{Sensor (4)} > \text{Disco Crítico/Adv (3/2)} > \text{Drive (2)} > \text{Temperatura (1)} = \text{Memoria (1)} > \text{OK (0)}$$

Mediante `union()`, ordenamiento descendente por `_value` y `limit(n: 1)` por estación, la celda de Diagnóstico Principal muestra exclusivamente el problema de mayor gravedad con colorimetría semántica en degradado de fila (`dark-red`, `dark-orange`, `semi-dark-yellow`, `green`).

### 2. Desacoplamiento de Alertas de Throttled y Umbral de Disco
- **Throttling Desvinculado**: Se eliminaron los umbrales de alerta en rojo para el estado `throttled`. Se preserva como un campo de texto informativo en el dashboard detallado `Health` (`0x0`, etc.).
- **Umbral de Disco Calibrado**: La alerta de disco se activa a partir del 90% de uso (menos del 10% de espacio disponible), evitando advertencias prematuras.

### 3. Filas Colapsables Temáticas en Dashboard Detallado (`health.json`)
Se reorganizaron los 18 paneles de diagnóstico profundo en 4 filas temáticas colapsables por defecto (`collapsed: true`):
1. **Salud del Sistema y Hardware (Raspberry Pi)** (`id: 30`)
2. **Salud de Adquisición (Ring Buffer Watchdog)** (`id: 20`)
3. **Integridad del Sensor Acelerométrico y Reloj** (`id: 23`)
4. **Sincronización con Google Drive** (`id: 26`)

Al hacer clic en la estación desde `SeismicMonitor`, el operador aterriza en `Health` con la estación preseleccionada (`var-station=...`), pudiendo desplegar de forma focalizada la fila vinculada al problema diagnosticado sin sobrecargar el navegador.

### 4. Arnés de Pruebas y Simulador Aislado (`simulador_alertas_mqtt.py`)
Para pruebas de integración confiables, se diseñó un simulador interactivo que publica simultáneamente en los 5 tópicos base (`state`, `health`, `acquisition`, `sensor`, `drive`), sobreescribiendo con datos nominales limpios al segundo UTC exacto todos los canales excepto el que se desea evaluar. Esto garantiza aislamiento total respecto a mensajes retenidos previos o telemetría de hardware de prueba en campo.

---

## Consecuencias

### Positivas
- **Claridad Operativa Inmediata**: Los operadores en sala de monitoreo identifican en segundos la naturaleza y gravedad del fallo en la pantalla general sin ambigüedades.
- **Cero Fatiga de Alertas por Throttling**: Se eliminan falsas alarmas persistentes derivadas de variaciones térmicas habituales en hardware embebido.
- **Rendimiento Optimizado en Grafana**: Las filas colapsadas preservan recursos del cliente y reducen sustancialmente la tasa de consultas concurrentes a InfluxDB hasta que el usuario expande la sección de interés.
- **Transición Fluida de lo General a lo Específico**: Navegación directa con Data Links entre la vista global (`SeismicMonitor`) y la inspección granular (`Health`).
- **Validación Automatizada y Reproducible**: El simulador de pruebas permite auditar cualquier escenario de alerta en segundos sin riesgo de traslapes ni procesos huérfanos.

### Negativas / Deuda Técnica
- **Enmascaramiento Jerárquico**: Una anomalía de mayor rango (ej. adquisición detenida) oculta en la matriz panorámica una advertencia de menor rango (ej. retención de Google Drive) hasta que el problema principal es resuelto, requiriendo que el operador inspeccione el dashboard `Health` para una revisión integral.
- **Mantenimiento del Filtro de Estaciones**: Si se adicionan nuevas estaciones a la red, debe actualizarse la expresión regular en la consulta Flux de `seismic_monitor.json`.
- **Apertura Manual de Filas en Grafana v11**: Debido a limitaciones en el soporte de URLs directas a paneles hijos colapsados en Grafana v11, las filas deben ser expandidas manualmente por el operador al navegar a `Health`.

---

## Referencias

- Diagnóstico de origen: [`2026-09-09_diagnostico_modelo_alertas_visualizacion_grafana.md`](https://github.com/RedSismicaAustro/RSA-Intern-TIG-MQTT/blob/main/docs/analysis/2026-09-09_diagnostico_modelo_alertas_visualizacion_grafana.md)
- Plan de implementación: [`plan_implementacion_alertas_visualizacion_grafana.md`](file:///home/rsa/.gemini/antigravity-ide/brain/8fd36331-d49a-4434-bf88-9c1ede03780e/plan_implementacion_alertas_visualizacion_grafana.md)
- Contextos técnicos relacionados:
  - [`seismic_monitor_context.md`](https://github.com/RedSismicaAustro/RSA-Intern-TIG-MQTT/blob/main/docs/context/seismic_monitor_context.md)
  - [`health_context.md`](https://github.com/RedSismicaAustro/RSA-Intern-TIG-MQTT/blob/main/docs/context/health_context.md)
  - [`telegraf_context.md`](https://github.com/RedSismicaAustro/RSA-Intern-TIG-MQTT/blob/main/docs/context/telegraf_context.md)
  - [`simulador_alertas_mqtt_context.md`](https://github.com/RedSismicaAustro/RSA-Intern-TIG-MQTT/blob/main/docs/context/simulador_alertas_mqtt_context.md)
