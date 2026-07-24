# Blueprint de Arquitectura: Sistema Web Modular de Análisis de Eventos Sísmicos (Fase 1: Visualizador)

**Fecha**: 2026-07-24  
**Repositorio**: `RSA-Intern-TIG-MQTT`  
**Autor**: Antigravity (Google DeepMind)  
**Destinatario**: Agente de Desarrollo / Antigravity IDE  

---

## 1. Visión General del Proyecto

Diseñar e implementar una aplicación Web interactiva basada en **Streamlit + ObsPy + Plotly** para inspeccionar, alinear y explorar eventos sísmicos de 120 segundos en formato MiniSEED subidos por las estaciones a Google Drive y disponibles localmente en `/home/rsa/datos_estaciones_drive/`.

El sistema estará containerizado e integrado al stack `docker-unified` y construido con una arquitectura modular en tubería (Pipeline), preparada para conectar en fases futuras los módulos de evaluación con modelos GPD (Original, TF, TFLite, Reentrenado), algoritmos tradicionales (STA/LTA) y rastreo de comandos MQTT.

---

## 2. Arquitectura de Archivos y Componentes

```text
RSA-Intern-TIG-MQTT/
├── services/
│   ├── docker-unified/
│   │   └── docker-compose.yml                 [MODIFICAR] Agregar servicio 'event-analyzer'
│   └── event-analyzer/                        [CREAR NUEVO DIRECTORIO]
│       ├── Dockerfile                         [CREAR] Python 3.11-slim + ObsPy + Streamlit + Plotly
│       ├── requirements.txt                   [CREAR] obspy, streamlit, plotly, pandas, numpy
│       ├── app.py                             [CREAR] Punto de entrada Streamlit UI
│       └── src/
│           ├── __init__.py
│           ├── core/
│           │   ├── reader.py                  [CREAR] Ingestor de archivos .mseed desde /data/events/
│           │   └── event_grouper.py           [CREAR] Agrupador de eventos regional por tiempo UTC
│           ├── modules/                       [DIRECTORIO DE MÓDULOS DEL PIPELINE]
│           │   ├── base.py                    [CREAR] Clase base abstracta BaseAnalysisModule
│           │   ├── visualizer.py              [CREAR] Módulo 1: Renderizador de formas de onda
│           │   └── gpd_validator.py           [RESERVADO FASE 3] Módulo 2: Validación GPD / STA-LTA
│           └── utils/
│               └── time_utils.py              [CREAR] Utilidades de formateo UTC y tiempo sismológico
```

---

## 3. Especificación Técnica de los Componentes

### 3.1. `services/docker-unified/docker-compose.yml`
Agregar el servicio `event-analyzer`:
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
    networks:
      - rsa_network
    environment:
      - DATA_DIR=/data/events
```

### 3.2. Estrategia de Ingesta y Agrupamiento (`reader.py` & `event_grouper.py`)
- **Ruta de escaneo**: `/data/events/<ESTACION>/events/*.mseed`
- **Agrupamiento por Evento Regional**:
  - Extraer fecha/hora UTC del stream ObsPy (`trace.stats.starttime`).
  - Agrupar trazas de distintas estaciones que coincidan dentro de una ventana de tiempo (ej. 30 segundos de diferencia de inicio) como un **Evento Regional Coincidente**.
  - Mantener los canales Z, N, E estructurados por estación.

### 3.3. Interfaz de Usuario (`app.py` & `visualizer.py`)
- **Barra Lateral**:
  - Selector de Evento por Fecha/Hora o Estación.
  - Opciones de Procesamiento:
    - Sin filtro (Raw).
    - Pasabanda Butterworth (Frecuencia mínima/máxima configurable, por defecto 0.5 - 20 Hz).
    - Desconectar línea base (Demean / Detrend).
- **Panel Principal**:
  - Visualización interactiva con Plotly (o Matplotlib en Streamlit).
  - Componentes Z, N, E alineadas temporalmente en UTC.
  - Hover informativo con amplitud exacta, hora HH:MM:SS.sss y estación.
- **Métricas de Cabecera**:
  - Estaciones participantes, PGA (Peak Ground Acceleration) estimado por canal, duración total del registro.

### 3.4. Patrón Pipeline Modular (`src/modules/base.py`)
```python
from abc import ABC, abstractmethod

class BaseAnalysisModule(ABC):
    @abstractmethod
    def get_name(self) -> str:
        pass

    @abstractmethod
    def process_event(self, event_stream_group) -> dict:
        """
        Recibe un grupo de streams de ObsPy correspondiente a un evento regional
        y retorna un diccionario con métricas, gráficos o decisiones de validación.
        """
        pass
```

---

## 4. Hoja de Ruta de Fases Futuras

* **Fase 1 (Este Blueprint)**: Visualizador de eventos extraídos en Streamlit + ObsPy en Docker.
* **Fase 2 (Rastreador de Mensajes MQTT)**: Integrar cliente MQTT (`paho-mqtt`) para formulario de extracción manual (`cmd/extract_event`) y visualización del ciclo de vida del evento (`Enviado` ➔ `Aceptado` ➔ `Completado` ➔ `Disponible en Drive`).
* **Fase 3 (Discriminación de Falsos Positivos)**: Evaluación con modelo GPD PyTorch/TensorFlow local, STA/LTA y filtrado automático.
