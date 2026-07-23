# Resumen de Sesión: Implementación del Correlador Regional de Eventos Sísmicos MQTT

**Fecha**: 2026-07-23  
**Repositorio**: `RSA-Intern-TIG-MQTT`  
**Agente de IA**: Antigravity (Google DeepMind)  
**Usuario**: Milton / RSA  

---

## 🎯 Objetivo de la Sesión

Diseñar, implementar e integrar un servicio centralizado de correlación de eventos sísmicos regionales en el servidor Ubuntu (`RSA-Intern-TIG-MQTT`). El objetivo principal fue cambiar el esquema de adquisición desde un modelo local autónomo hiper-sensible (donde cada estación extraía y subía a Google Drive de forma individual) a un modelo de **extracción coordinada y validada en red (evento regional)**.

---

## 📂 Archivos Creados y Modificados

```text
montajes/server-ubuntu/rsa/RSA-Intern-TIG-MQTT/
│
├── README.md                                         [MODIFICADO] Actualización de arquitectura, tópicos y estructura
│
├── docs/
│   ├── context/
│   │   └── regional_event_correlator_context.md      [NUEVO] Documentación técnica detallada y diagramas Mermaid
│   └── progress/
│       └── 2026-07-23_contexto-agente.md             [NUEVO] Este documento de transición
│
├── scripts/
│   └── correlator/                                   [NUEVO DIRECTORIO]
│       ├── .env.example                              [NUEVO] Plantilla de variables de entorno para MQTT
│       ├── config.json                               [NUEVO] Configuración de umbrales (10s, min 2 est, delete_after_upload: true)
│       ├── Dockerfile                                [NUEVO] Imagen Docker basada en python:3.11-slim (unbuffered)
│       ├── regional_event_correlator.py              [NUEVO] Script daemon principal de correlación MQTT
│       └── requirements.txt                          [NUEVO] Dependencias (paho-mqtt, python-dotenv)
│
└── services/
    └── docker-unified/
        └── docker-compose.yml                        [MODIFICADO] Integración del servicio 'correlator' al stack
```

---

## 🛠️ Diagnóstico y Modificaciones Realizadas

### 1. Cambio de Paradigma de Extracción en la Red
* **En las Estaciones (`acelerografo-DEV00`):** Se cambió la configuración a `"auto_extract": false` y `"auto_upload": false`. Con esto, ante alertas locales de GPD, el script `gpd_stream_worker.py` publica el aviso en `rsa/seismic/smart/<station_id>/events/detected`, pero no ejecuta la extracción local ni la subida a Drive.
* **En el Servidor (`RSA-Intern-TIG-MQTT`):** Se creó el servicio `regional_event_correlator.py` que se suscribe a todas las alertas individuales de las estaciones.

### 2. Algoritmo de Correlación e Inmunidad al Ruido
* **Desduplicación por Estación:** El correlador filtra ruidos masivos o múltiples alertas consecutivas de una misma estación dentro del rango de coincidencia, manteniendo una sola entrada por estación.
* **Coincidencia Temporal (10s):** Evalúa si **2 o más estaciones distintas** reportan una alerta dentro de un margen temporal configurable (10 segundos).
* **Disparo Broadcast Masivo:** Al confirmar el evento regional, publica la orden de extracción en `rsa/seismic/smart/broadcast/cmd/extract_event` ordenando la extracción, subida a Drive y borrado local (`"delete_after_upload": true`).

### 3. Contenedorización en Docker Compose
* Se empaquetó el servicio bajo la imagen `rsa-correlator` en `services/docker-unified/docker-compose.yml`, integrándolo al stack unificado junto a InfluxDB, Telegraf y Grafana bajo la red `rsa_network`.

---

## 📊 Validación en Entorno Real (Logs Confirmados)

Durante las pruebas en caliente, dos estaciones (`CHA2` y `DEV0`) generaron detecciones coincidentes en menos de 10 segundos. El comportamiento observado fue:

1. **Detección:** `[EVENTO_REGIONAL_CONFIRMADO] 🚨 Coincidencia detectada en 2 estaciones (CHA2, DEV0) dentro de ventana de 10.0s!`
2. **Broadcast:** Publicación exitosa de `req_id=corr-20260721-225225` con `delete_after_upload=True`.
3. **Respuesta de Red:** Las 6 estaciones en línea enviaron el ACK `status=accepted`.
4. **Finalización:** 4 estaciones (`DEV0`, `DEV01`, `CHA2`, `CHA1`) recortaron los archivos MiniSEED, los subieron a Google Drive y confirmaron `status=completed`, dejando el almacenamiento local limpio.

---

## 📋 Pasos Sugeridos para la Siguiente Sesión

1. **Monitoreo de Estabilidad:**
   * Revisar los logs del servicio contenedorizado desde `services/docker-unified/` mediante `docker compose logs -f correlator`.
2. **Ajuste Fino de Umbrales:**
   * En caso de requerir ajustar la ventana temporal o el número mínimo de estaciones según la densidad de la red, modificar [config.json](file:///home/rsa/git/montajes/server-ubuntu/rsa/RSA-Intern-TIG-MQTT/scripts/correlator/config.json).
3. **Módulos de Análisis Futuros:**
   * Si se requiere implementar visualización o análisis científico de ondas MiniSEED en el servidor (ej. con ObsPy / Streamlit / Dash), agregar un contenedor hermano en `docker-compose.yml`.
