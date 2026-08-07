# Resumen de Sesión: Selección por Calendario, Resampling Dinámico (Plotly-Resampler) y Optimización de Event Analyzer

**Fecha**: 2026-08-06  
**Repositorio**: `RSA-Intern-TIG-MQTT`  
**Agente de IA**: Antigravity (Google DeepMind)  
**Usuario**: Milton / RSA  

---

## 🎯 Objetivo de la Sesión

Optimizar e integrar nuevas capacidades de usabilidad, rendimiento y precisión sismológica al servicio **Event Analyzer** (`services/event-analyzer`). Los metas alcanzadas fueron:
1. Implementar la selección reactiva de eventos regionales mediante un widget de calendario (`st.date_input`) y un botón explicito (`✅ Aplicar Selección de Eventos`), eliminando la renderización automática prematura.
2. Resolver el fallo de desbordamiento de payload WebSocket (`MessageSizeError > 200 MB`) y cuelgues del navegador.
3. Integrar **`plotly-resampler`** con un micro-servidor asíncrono Dash en el puerto `8050` para servir vistas iniciales diezmadas a 3,000 puntos y re-computar dinámicamente muestras a resolución nativa de 100-200 Hz al hacer zoom (esencial para la picada exacta de ondas P y S).
4. Configurar la infraestructura Docker para exposición de puertos (`8050:8050`) y montaje bind de desarrollo (`../event-analyzer:/app`).

---

## 📂 Estructura del Repositorio Implementada y Modificada

```text
montajes/ubuntu-server/rsa/RSA-Intern-TIG-MQTT/
├── docs/
│   ├── context/
│   │   └── event_analyzer_context.md                 [MODIFICADO] Actualización de arquitectura, diagramas Mermaid, LOCs y plotly-resampler
│   └── progress/
│       └── 2026-08-06_contexto-agente.md             [MODIFICADO] Este documento de transición técnica
│
└── services/
    ├── docker-unified/
    │   └── docker-compose.yml                        [MODIFICADO] Adición del volumen bind y exposición del puerto 8050:8050
    └── event-analyzer/
        ├── requirements.txt                          [MODIFICADO] Inclusión de plotly-resampler>=0.9.1
        ├── app.py                                    [MODIFICADO] Selección por calendario, register_plotly_resampler y estado reactivo
        └── src/
            └── modules/
                └── visualizer.py                     [MODIFICADO] FigureResampler (3k pts iniciales, zoom dinámico hf_x/hf_y)
```

---

## ⚙️ Configuración del Entorno y Despliegue Docker

* **Montaje Bind y Puertos Expuestos (`docker-compose.yml`)**:
  - Se añadió la ruta `- ../event-analyzer:/app` al contenedor `rsa-event-analyzer`.
  - Se expuso el puerto `8050:8050` e inyectó la variable de entorno `RESAMPLER_HOST=${RESAMPLER_HOST:-ubuntu-server}` para permitir peticiones AJAX/WebSockets de resampling en la LAN.
  - **Construcción**: Requiere `docker compose up -d --build event-analyzer` para compilar la nueva dependencia de `requirements.txt`.

---

## 🛠️ Modificaciones de Código y Refactorización

### 1. Selección por Calendario y Estado Reactivo (`app.py`)
- **Agrupamiento por Fecha**: Se indexaron las trazas agrupando por `evt.reference_time_utc.date()`.
- **Calendario `st.date_input`**: Delimitado por el rango de fechas con registros sísmicos en la red.
- **Desplegable Diario**: El menú de selección se filtra reactivamente según la fecha elegida.
- **Estado Inicial en Blanco**: Asignación de `st.session_state.applied_event_label = None` con `st.stop()` para evitar cargas pesadas involuntarias hasta presionar **"✅ Aplicar Selección de Eventos"**.

### 2. Resampling Dinámico de Alta Resolución (`visualizer.py` y `app.py`)
- **Problema Sismológico**: El diezmado estático (`[::step]`) perdía la resolución temporal nativa de las muestras (100-200 Hz) al hacer zoom para picar el inicio de fases P y S.
- **Solución con `plotly-resampler`**:
  - Se envolvió la figura con `FigureResampler(sub_fig, default_n_shown_samples=3000)` e inyectaron las trazas crudas mediante `hf_x` y `hf_y`.
  - Se registró `register_plotly_resampler(mode="Dash", port=8050, host="0.0.0.0")` en `app.py`.
- **Resultado Verificado (F12 Console)**: La gráfica inicial se sirve diezmada a 3,025 puntos (~2 MB payload, carga en <2s). Al hacer zoom en una ventana de interés (ej. 3 segundos), el servidor recalcula y sirve el 100% de las muestras crudas nativas para la picada exacta de fases P y S.

---

## 📋 Pasos Sugeridos para el Siguiente Agente

1. **Revisar Documentación y ADRs Generados**:
   - Leer ADR-013: [rsa/RSA-Metodologias/decisiones/013_downsampling_trazas_y_estado_reactivo_event_analyzer.md](file:///home/rsa/git/rsa/RSA-Metodologias/decisiones/013_downsampling_trazas_y_estado_reactivo_event_analyzer.md).
   - Leer ADR-014: [rsa/RSA-Metodologias/decisiones/014_resampling_dinamico_alta_resolucion_plotly_resampler.md](file:///home/rsa/git/rsa/RSA-Metodologias/decisiones/014_resampling_dinamico_alta_resolucion_plotly_resampler.md).
   - Leer el contexto técnico actualizado: [docs/context/event_analyzer_context.md](file:///home/rsa/git/montajes/ubuntu-server/rsa/RSA-Intern-TIG-MQTT/docs/context/event_analyzer_context.md).
2. **Implementar Fase 2 (Control MQTT en Event Analyzer)**:
   - Integrar un cliente `paho-mqtt` en `event-analyzer` para enviar órdenes manuales de extracción `rsa/seismic/smart/{target_id}/cmd/extract_event` directamente desde la interfaz web de Streamlit.
3. **Planificar Fase 3 (Clasificación Automatizada GPD / STA-LTA)**:
   - Diseñar un nuevo módulo bajo `BaseAnalysisModule` en `src/modules/gpd_validator.py` para evaluación automática de trazas con el modelo GPD o STA/LTA.
