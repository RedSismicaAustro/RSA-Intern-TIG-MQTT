# Resumen de Sesión: Configuración de Google Drive y Diseño del Sistema Web Modular de Análisis Sísmico

**Fecha**: 2026-07-24  
**Repositorio**: `RSA-Intern-TIG-MQTT`  
**Agente de IA**: Antigravity (Google DeepMind)  
**Usuario**: Milton / RSA  

---

## 🎯 Objetivo de la Sesión

1. Configurar y montar permanentemente la carpeta de Google Drive `"DIA/Datos Estaciones"` en el servidor Ubuntu 24.04 mediante un servicio `systemd` y `rclone`.
2. Diagnosticar la causa de falsos positivos en las extracciones de eventos sísmicos (algoritmo GPD en TFLite en estaciones).
3. Diseñar la arquitectura técnica del **Sistema Web Modular de Análisis de Eventos Sísmicos (Streamlit + ObsPy + Docker)** para visualizar y analizar eventos de 120s en formato MiniSEED.
4. Elaborar el plano de arquitectura (Blueprint) para la Fase 1 y acordar la hoja de ruta para las Fases 2 (Control & Tracking MQTT) y 3 (Discriminación GPD/STA-LTA).

---

## 📂 Estructura de Archivos Creados y Modificados

```text
RSA-Intern-TIG-MQTT/
├── docs/
│   ├── blueprints/
│   │   └── 2026-07-24_event-analyzer-phase1-blueprint.md [NUEVO] Blueprint detallado de arquitectura para Fase 1
│   └── progress/
│       ├── 2026-07-23_contexto-agente.md                  [EXISTENTE] Contexto del Correlador Regional
│       └── 2026-07-24_contexto-agente.md                  [NUEVO] Este documento de transición técnica
```

### Configuración en el Servidor Ubuntu Remoto (Fuera del Repositorio)
* **Punto de montaje de Google Drive**: `/home/rsa/datos_estaciones_drive`
* **Servicio Systemd creado**: `/etc/systemd/system/rclone-gdrive.service` (Estado: `active (running)`).
* **Acceso FUSE habilitado**: `user_allow_other` configurado en `/etc/fuse.conf` para permitir lectura/escritura a contenedores Docker.

---

## ⚙️ Diagnóstico y Decisión de Arquitectura

### 1. Integración de Google Drive (`rclone`)
* Se restauró la autenticación OAuth2 expirada mediante `rclone config reconnect gdrive:`.
* Se comprobó la lectura de las subcarpetas de estaciones: `CHA01`, `CHA02`, `DEV00`, `DEV01`, `FERR`, `LAB01`, `OBSID`, `PRM01`, `PRM02`, `TENG`, `TST1`.
* El servicio automontado expone las trazas `.mseed` bajo el esquema: `/home/rsa/datos_estaciones_drive/<STATION>/events/<STATION_PREFIX>_<YYYYMMDD_HHMMSS>.mseed`.

### 2. Estrategia Modular por Fases
Se acordó dividir el sistema de análisis en 3 fases continuas:
* **Fase 1 (Próxima Implementación)**: Aplicación Web en Streamlit (`event-analyzer`) para ingesta y visualización alineada UTC de eventos de 120s multiestación.
* **Fase 2**: Integración de la interfaz de control de extracción manual MQTT (`cmd/extract_event`) y rastreo del ciclo de vida del evento (`Enviado` ➔ `Aceptado` ➔ `Completado` ➔ `Disponible en Drive`).
* **Fase 3**: Integración de los módulos de evaluación GPD (Original, TF, TFLite, Reentrenado) y STA/LTA para filtrado automático de falsos positivos.

---

## 🛠️ Especificaciones para la Fase 1 (Visualizador Web)

* **Servicio Docker**: `event-analyzer` expuesto en el puerto `8501`, agregado a `services/docker-unified/docker-compose.yml`.
* **Volumen**: `/home/rsa/datos_estaciones_drive:/data/events:ro`.
* **Librerías clave**: Python 3.11, `obspy`, `streamlit`, `plotly`, `pandas`, `numpy`.
* **Patrón de Software**: Tubería de análisis extensible mediante `BaseAnalysisModule` en `src/modules/base.py`.

---

## 📋 Pasos Sugeridos para el Siguiente Agente

1. **Revisar el Blueprint de Arquitectura**:
   * Leer atentamente [2026-07-24_event-analyzer-phase1-blueprint.md](file:///c:/Users/miltonrsa/Documents/git/rsa/RSA-Intern-TIG-MQTT/docs/blueprints/2026-07-24_event-analyzer-phase1-blueprint.md).
2. **Crear la Estructura del Servicio `event-analyzer`**:
   * Crear el directorio `services/event-analyzer/` con su `Dockerfile` y `requirements.txt`.
3. **Implementar los Módulos Python Core**:
   * `src/core/reader.py`: Ingestor de archivos `.mseed` desde `/data/events/`.
   * `src/core/event_grouper.py`: Agrupador de eventos regionales por proximidad de tiempo UTC.
   * `src/modules/base.py` y `src/modules/visualizer.py`: Renderizador interactivo en Plotly.
   * `app.py`: Punto de entrada de la interfaz Streamlit.
4. **Integrar en Docker Compose**:
   * Actualizar `services/docker-unified/docker-compose.yml` para incluir `event-analyzer` en la red `rsa_network`.
5. **Validar y Desplegar**:
   * Levantar el stack con `docker compose up -d` y verificar la visualización en `http://localhost:8501`.
