---
proyecto: RSA-Intern-TIG-MQTT
tipo: contexto_tecnico
archivo: services/event-analyzer/app.py
temas: [streamlit, obspy, plotly, event-analyzer, miniseed, docker-compose, dsp, lazy-loading]
---
# Visualizador Web de Eventos Sísmicos (Event Analyzer) — Contexto para Agentes IA

> Aplicación Web containerizada en Streamlit + ObsPy + Plotly para la ingesta, alineación temporal UTC, procesamiento DSP y exploración gráfica interactiva multiestación de eventos sísmicos en formato MiniSEED almacenados en Google Drive.

**Ruta**: `services/event-analyzer/app.py`  
**Rutas de Archivos Asociados**:
- Ingestor por Expresión Regular: `services/event-analyzer/src/core/reader.py`
- Agrupador Regional UTC: `services/event-analyzer/src/core/event_grouper.py`
- Clase Base Pipeline: `services/event-analyzer/src/modules/base.py`
- Renderizador de Formas de Onda: `services/event-analyzer/src/modules/visualizer.py`
- Utilidades de Tiempo: `services/event-analyzer/src/utils/time_utils.py`
- Tema Visual RSA: `services/event-analyzer/.streamlit/config.toml`
- Dockerfile: `services/event-analyzer/Dockerfile`
- Dependencias: `services/event-analyzer/requirements.txt`
- Integración Docker Compose: `services/docker-unified/docker-compose.yml`

**LOC**: `app.py`: 160 | `reader.py`: 86 | `event_grouper.py`: 90 | `visualizer.py`: 165 | `base.py`: 20 | `time_utils.py`: 22 | `Dockerfile`: 16  
**Lenguaje/Formato**: Python 3.11, Streamlit UI, TOML, Dockerfile, YAML  
**Dependencias/Librerías**: `obspy>=1.4.0`, `streamlit>=1.30.0`, `plotly>=5.18.0`, `pandas>=2.0.0`, `numpy>=1.24.0`  
**Proceso**: Servicio contenedorizado (`rsa-event-analyzer`) expuesto en el puerto `8501`, parte del stack `docker-unified` en la red `rsa_network` (`monitoring`).

---

## 🎯 Arquitectura y Flujo de Datos

El sistema opera como una tubería (Pipeline) de lectura, agrupamiento y visualización dividida en las siguientes fases:

1. **Escaneo por Expresión Regular (`reader.py`)**:
   - Escanea el punto de montaje de Google Drive (`/data/events` $\leftarrow$ `/home/rsa/datos_estaciones_drive`).
   - Aplica la expresión regular `FILENAME_PATTERN = r"^([A-Za-z0-9]+)_(\d{8})_(\d{6})\.(?:mseed|MSEED)$"` sobre los nombres de archivo.
   - Extrae el código de la estación y la fecha/hora de inicio UTC sin ejecutar lecturas de disco/red con ObsPy durante la ingesta inicial, garantizando un listado instantáneo.
2. **Agrupamiento Regional UTC (`event_grouper.py`)**:
   - Ordena las trazas cronológicamente por `start_utc`.
   - Agrupa trazas de distintas estaciones cuyo tiempo de inicio coincida dentro de una ventana configurable (30 segundos).
   - Genera identificadores únicos de evento (`EVT-YYYYMMDD-HHMMSS`) y mantiene referencias ligeras a `EventFile` (*Lazy Loading*).
3. **Interfaz de Usuario Streamlit (`app.py`)**:
   - Presenta una barra lateral con selector de evento regional, filtro de estaciones participantes y controles de procesamiento DSP (detrending y filtro pasabanda Butterworth).
   - Incluye formularios independientes (`st.form`) con botones de confirmación (`✅ Aplicar Selección de Estaciones` y `⚡ Aplicar Filtros DSP`) para evitar renderizados automáticos innecesarios.
4. **Carga Bajo Demanda y Procesamiento DSP (`visualizer.py`)**:
   - Al seleccionar y confirmar un evento, invoca `regional_event.load_streams()`, cargando con ObsPy únicamente las trazas MiniSEED de las estaciones requeridas.
   - Aplica `st_copy.detrend("demean")` y `st_copy.detrend("linear")` para remover tendencia/media.
   - Aplica filtro pasabanda Butterworth de 4to orden con fase cero (`tr.filter("bandpass", ...)`).
   - Construye una figura Plotly `make_subplots` multi-canal (Z, N, E) alineada temporalmente en UTC con paleta de colores por estación e interacción *hover*.

```mermaid
graph TD
    subgraph Google Drive Mount (/data/events)
        DriveFiles[Archivos .mseed en Subcarpetas de Estaciones]
    </div>

    subgraph Core Ingestion (Fast Scanning)
        DriveFiles -->|1. Listado de Nombres| Reader[MseedReader: reader.py]
        Reader -->|2. Regex Parsing sin ObsPy| EventFiles[Lista de EventFile Metadata]
        EventFiles -->|3. Proximidad UTC < 30s| Grouper[EventGrouper: event_grouper.py]
        Grouper -->|4. Agrupamiento| RegionalEvents[Lista de RegionalEvent Metadata]
    end

    subgraph Interface & State (app.py)
        RegionalEvents -->|5. Muestra Lista| Dropdown[Sidebar: Selector de Evento]
        Dropdown -->|6. Evento Seleccionado| State[st.session_state & Formularios]
        Form1[Form: Estaciones Seleccionadas] -->|Confirmación ✅| State
        Form2[Form: Filtros DSP] -->|Confirmación ⚡| State
    end

    subgraph Pipeline & Rendering (visualizer.py)
        State -->|7. Lazy Loading por Demanda| Load[load_streams: ObsPy Read]
        Load -->|8. Detrend & Pasabanda| DSP[Procesamiento DSP]
        DSP -->|9. Render Subplots UTC| Plotly[Plotly Multi-trace Subplots]
    end

    Plotly -->|10. Gráfico Interactivo| Operador((Operador / Sismólogo en :8501))
```

---

## ⚙️ Configuraciones y Variables de Entorno

### Variables del Entorno Docker (`docker-compose.yml`)
- `DATA_DIR=/data/events`: Ruta interna dentro del contenedor donde se montan las trazas sísmicas.
- `TZ=America/Guayaquil`: Zona horaria para concordancia de logs locales.

### Puertos Expuestos
- `8501:8501`: Puerto nativo para acceder a la aplicación web Streamlit.

### Volúmenes de Persistencia e Integración
- `/home/rsa/datos_estaciones_drive:/data/events:ro`: Montaje en modo **solo lectura** del directorio de Google Drive mantenido por el servicio `rclone`.

---

## 🛠️ Componentes y Clases Clave

| Clase / Módulo | Archivo | Propósito / Función |
|----------------|---------|---------------------|
| `MseedReader` | `src/core/reader.py` | Ingestor con parseo regex de nombres de archivo `ID_YYYYMMDD_HHMMSS.mseed`. Evita la sobrecarga FUSE durante el escaneo inicial. |
| `EventFile` | `src/core/reader.py` | DataClass liviana que almacena metadatos de traza y el método `load_stream()` para carga por demanda. |
| `EventGrouper` | `src/core/event_grouper.py` | Motor de coincidencia temporal UTC que agrupa trazas multiestación en objetos `RegionalEvent`. |
| `RegionalEvent` | `src/core/event_grouper.py` | Contenedor de evento regional con cálculo de estación, duración y método `load_streams()` para ObsPy. |
| `BaseAnalysisModule` | `src/modules/base.py` | Clase abstracta para los módulos del pipeline. Define `get_name()` y `process_event(...)`. |
| `WaveformVisualizer` | `src/modules/visualizer.py` | Hereda de `BaseAnalysisModule`. Aplica DSP (`detrend("demean")` / `filter("bandpass")`) y genera gráficos Plotly interactivos. |
| `time_utils.py` | `src/utils/time_utils.py` | Funciones auxiliares para formateo de tiempos UTC/locales y duraciones. |

---

## 🐳 Integración Docker Compose (`services/docker-unified/docker-compose.yml`)

El servicio está integrado como la 5ta unidad del stack unificado:

```yaml
  event-analyzer:
    build:
      context: ../event-analyzer
      dockerfile: Dockerfile
    container_name: rsa-event-analyzer
    restart: unless-stopped
    ports:
      - "8501:8501"
    volumes:
      - /home/rsa/datos_estaciones_drive:/data/events:ro
    environment:
      - DATA_DIR=/data/events
      - TZ=America/Guayaquil
    networks:
      - monitoring
```

### Operación y Despliegue

```bash
# Arrancar o recompilar el servicio dentro del stack
cd services/docker-unified
docker compose up -d --build event-analyzer

# Monitorear logs en tiempo real
docker compose logs -f event-analyzer
```

---

## 📌 Limitaciones Conocidas y Pasos Futuros

- **Formato de Nombre Requerido**: El escaneo ultra rápido asume la convención `<ESTACION>_<YYYYMMDD>_<HHMMSS>.mseed`. Si un archivo posee un nombre no estandarizado, recurre a un *fallback* basado en la fecha de modificación del sistema de archivos.
- **Sin Autenticación HTTP**: La interfaz en el puerto 8501 no posee login nativo (adecuado para red interna/VPN). Si se expone a internet, se recomienda un proxy inverso Nginx con autenticación básica.
- **Preparado para Fase 2 y 3**: La estructura bajo `BaseAnalysisModule` permite conectar en las siguientes fases el módulo de control MQTT (`cmd/extract_event`) y los clasificadores GPD / STA-LTA para filtrado de falsos positivos.
