# Resumen de Sesión: Diseño para Centralización en InfluxDB e Ingesta de Eventos Sísmicos

**Fecha de creación:** 13 de agosto de 2026  
**Destinatario:** Agente de IA / Contexto de Sesión Futura  
**Proyecto:** RSA-Intern-TIG-MQTT (Monitoreo Sísmico TIG Stack + MQTT)  
**Directorio de Trabajo Exclusivo:** `montajes/ubuntu-server/rsa/RSA-Intern-TIG-MQTT`

---

## 1. Contexto Inicial y Lectura de Archivos
Al inicio de la sesión, se leyeron y analizaron los documentos de progreso y contexto del proyecto ubicados en:
* `docs/progress/` (archivos del 23 de julio, 24 de julio, 5 de agosto y 6 de agosto de 2026).
* `docs/context/regional_event_correlator_context.md`
* `docs/context/event_analyzer_context.md`

### Resumen del Estado Tecnológico:
* **Correlador Regional MQTT** (`regional_event_correlator.py`): Servicio daemon en Docker que procesa alertas en `rsa/seismic/smart/+/events/detected`. Si $\ge 2$ estaciones coinciden en una ventana de 10s (`ventana_coincidencia_s`), confirma un evento regional y envía un comando broadcast de extracción masiva en `rsa/seismic/smart/broadcast/cmd/extract_event` (`delete_after_upload: true`).
* **Event Analyzer** (`app.py`): Visualizador web en Streamlit. Realiza escaneo por expresión regular sobre los nombres de archivo MiniSEED en el punto de montaje de Google Drive (`/data/events` $\leftarrow$ `datos_estaciones_drive`) para listado instantáneo. Agrupa por ventanas de 30s en eventos regionales y aplica *Lazy Loading* con ObsPy, DSP y `plotly-resampler` (puerto 8050) para visualización interactiva.

---

## 2. Requerimientos del Usuario
El usuario planteó la necesidad de almacenar el registro de eventos detectados en una base de datos InfluxDB con los siguientes objetivos:
1. **Optimización del Ingestor**: Evitar el escaneo y parseo regex de miles de archivos MiniSEED en Google Drive en el arranque o recarga de la aplicación web `Event Analyzer`, logrando una consulta de metadatos instantánea mediante consultas directas a la base de datos de series temporales.
2. **Enriquecimiento Visual**: Registrar y mostrar qué estaciones específicas detectaron cada evento en la sección *"Ver Metadatos del Evento y Archivos de Trazas"* en la UI de Streamlit.
3. **Clasificación de Eventos**: El sistema debe registrar y evaluar 4 tipos de eventos sísmicos:
   * **Tipo 1**: Eventos detectados automáticamente por el correlador regional.
   * **Tipo 2**: Eventos extraídos manualmente por el usuario a través de Node-RED (servicio a retirar en la Fase 2).
   * **Tipo 3**: Eventos confirmados en el visualizador `Event Analyzer` (desarrollo futuro).
   * **Tipo 4**: Eventos descartados en el visualizador `Event Analyzer` (desarrollo futuro).

---

## 3. Propuestas y Decisiones de Arquitectura Diseñadas
Durante la discusión, se estructuraron las siguientes soluciones arquitectónicas:

### Ingesta y Flujos a InfluxDB mediante Telegraf y MQTT
* **Para los Eventos Tipo 1 y 2 (Generados por MQTT)**:
  * Se acordó que **Telegraf** es la herramienta ideal y más eficiente (en lugar de Node-RED) para escuchar los tópicos del Broker MQTT en tiempo real e insertar automáticamente los registros en InfluxDB.
* **Para los Eventos Tipo 3 y 4 (Confirmados/Descartados en Streamlit)**:
  * Escribir directamente desde Streamlit a una base de datos InfluxDB local rompería la consistencia entre servidores independientes (ej. Casa vs Oficina).
  * **Solución**: Se sugirió que el `Event Analyzer` **publique un mensaje MQTT** con la acción tomada (ej. en el tópico `rsa/seismic/smart/events/status` con payload `{"status": "confirmed" | "discarded"}`). De esta manera, los agentes Telegraf distribuidos en cualquier máquina de la red (Casa/Oficina) consumirán este mensaje e inyectarán el estado en sus respectivos InfluxDB, manteniendo ambas bases de datos sincronizadas en tiempo real mediante un flujo impulsado por eventos (*event-driven*).

### Solución para la Sincronización (Casa vs Oficina) e InfluxDB en VPS
* **Restricción del Entorno**: El servidor de la oficina está detrás del firewall de la universidad, el cual prohíbe el uso de Tailscale o VPNs similares. La base de datos InfluxDB actual de la oficina pesa **342 MB** (acumulados para 3 meses de retención).
* **Propuesta**: Centralizar la base de datos InfluxDB alojándola en el mismo VPS que ejecuta el Broker MQTT (un VPS básico de **1 vCPU / 1 GB RAM / 25 GB Disk**).
* **Viabilidad Técnica y Recomendaciones**:
  * **Almacenamiento (Disco)**: Totalmente viable. 342 MB cada 3 meses representan aproximadamente 1.3 GB al año, por lo que 25 GB de disco en el VPS ofrecen espacio suficiente para varios años.
  * **Memoria RAM (Punto crítico de falla)**: InfluxDB v2 está escrito en Go y consume bastante RAM. 1 GB de RAM física total compartida con el SO y Mosquitto MQTT es extremadamente ajustado y el *OOM Killer* de Linux podría apagar servicios.
  * **Estrategia de Mitigación Obligatoria en el VPS**:
    1. **Crear Swap**: Configurar de manera obligatoria un archivo de intercambio Swap de al menos 2 GB en el disco SSD del VPS.
    2. **Límites de Recursos Docker**: Limitar los recursos del contenedor de InfluxDB en su `docker-compose.yml` (ej. `deploy.resources.limits.memory: 600M`) y definir la variable de entorno de Go `GOMEMLIMIT=500m` para una recolección de basura agresiva.
    3. **Filtrado de Métricas**: Solo almacenar metadatos de eventos (baja frecuencia). Si se requiere telemetría de alta frecuencia (estado de estaciones cada 10s), esto saturará la memoria del VPS de 1GB.
    4. **Seguridad**: Configurar el firewall (`ufw`) del VPS para restringir el acceso al puerto `8086` o configurar un proxy reverso con TLS/HTTPS y tokens muy seguros.

---

## 4. Siguientes Pasos Recomendados para la Sesión de Desarrollo
El próximo agente de desarrollo deberá encarar los siguientes puntos:
1. **Configurar el InfluxDB en el VPS**: Asegurar los límites de recursos de Docker Compose, crear el archivo Swap en el servidor del VPS y habilitar reglas seguras de Firewall.
2. **Definir la Estructura de Tópicos MQTT y Esquema de InfluxDB**: Acordar la estructura de datos (Measurements, Fields y Tags) para registrar los 4 tipos de eventos y sus estaciones involucradas.
3. **Modificar el Correlador Regional**: Implementar la publicación MQTT del evento confirmado con los detalles del trigger y las estaciones asociadas.
4. **Configurar Telegraf**: Configurar el archivo `telegraf.conf` para mapear los tópicos del correlador regional y actualizar la base de datos InfluxDB central.
5. **Actualizar el Event Analyzer**: Integrar la consulta a InfluxDB mediante la librería `influxdb-client-python` para poblar el visualizador Streamlit y añadir la funcionalidad de publicación MQTT para confirmación/descarte de eventos.
