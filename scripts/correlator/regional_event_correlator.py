#!/usr/bin/env python3
"""
regional_event_correlator.py — Servicio de Correlación Regional de Eventos Sísmicos.

Servicio daemon que:
1. Se suscribe a todas las alertas de detecciones individuales publicadas por las estaciones
   en el tópico: {org}/{app}/{cap}/+/events/detected
2. Mantiene un buffer temporal deslizante en memoria de las detecciones recientes.
3. Descarta múltiples detecciones de una misma estación dentro del intervalo de coincidencia (filtrado de ruido).
4. Evalúa si 2 o más estaciones distintas reportaron detección dentro de una ventana temporal
   configurable (ej. 10 segundos).
5. Al confirmar un evento regional, publica la orden de extracción masiva en el canal broadcast:
   {org}/{app}/{cap}/broadcast/cmd/extract_event
   con las banderas "upload": true y "delete_after_upload": true.
"""

import json
import logging
import os
import signal
import socket
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from dotenv import load_dotenv

try:
    import paho.mqtt.client as mqtt_client
    _MQTT_AVAILABLE = True
except ImportError:
    print("[ERROR] paho-mqtt no está instalado. Instálalo con: pip install paho-mqtt", file=sys.stderr)
    sys.exit(1)


def timestamp_iso(dt: Optional[datetime] = None) -> str:
    """Retorna timestamp en formato ISO 8601 UTC con sufijo 'Z'."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class RegionalEventCorrelator:
    """Coordinador y Correlador de Eventos Sísmicos Regionales en tiempo real."""

    def __init__(self, config_path: str, logger: logging.Logger):
        self.logger = logger
        self.config = self._cargar_configuracion(config_path)

        # Extraer parámetros de correlación
        corr_cfg = self.config.get("correlador", {})
        self.min_estaciones: int = int(corr_cfg.get("min_estaciones", 2))
        self.ventana_coincidencia_s: float = float(corr_cfg.get("ventana_coincidencia_s", 10.0))
        self.cooldown_evento_s: float = float(corr_cfg.get("cooldown_evento_s", 60.0))
        self.ventana_pre_evento_s: int = int(corr_cfg.get("ventana_pre_evento_s", 60))
        self.ventana_post_evento_s: int = int(corr_cfg.get("ventana_post_evento_s", 60))
        self.delete_after_upload: bool = bool(corr_cfg.get("delete_after_upload", True))

        # Tópicos
        org = self.config.get("org", "rsa")
        app = self.config.get("app", "seismic")
        cap = self.config.get("cap", "smart")
        
        self.topic_sub = self.config["topics"]["events_subscription"].format(org=org, app=app, cap=cap)
        self.topic_metadata = self.config["topics"].get(
            "events_metadata", "{org}/{app}/{cap}/events/metadata"
        ).format(org=org, app=app, cap=cap)
        self.topic_broadcast = self.config["topics"]["cmd_broadcast"].format(org=org, app=app, cap=cap)
        self.topic_res = self.config["topics"]["cmd_response_sub"].format(org=org, app=app, cap=cap)

        # Estado del buffer en memoria
        # Lista de dicts: [{"station_id": str, "dt": datetime, "type": str, "prob": float, "raw": dict}]
        self.buffer_detecciones: List[dict] = []
        self.last_broadcast_time: float = 0.0
        self.running: bool = False
        self.mqtt_client: Optional[object] = None

    def _cargar_configuracion(self, config_path: str) -> dict:
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Archivo de configuración no encontrado: {config_path}")
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def iniciar(self) -> None:
        self.running = True
        
        # Registrar señales de parada ordenada
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        self.logger.info(
            f"[CORRELATOR_INIT] Iniciando Correlador Regional RSA | "
            f"min_estaciones={self.min_estaciones}, ventana={self.ventana_coincidencia_s}s, "
            f"cooldown={self.cooldown_evento_s}s, delete_after_upload={self.delete_after_upload}"
        )

        # Cargar variables de entorno
        broker_host = os.getenv("MQTT_BROKER", "localhost")
        broker_port = int(os.getenv("MQTT_PORT", 1883))
        username = os.getenv("MQTT_USERNAME")
        password = os.getenv("MQTT_PASSWORD")

        # Client ID fijo para sesión persistente en Mosquitto.
        # Permite que el broker retenga mensajes con QoS 1 ante cortes de energía o reinicios.
        client_id = os.getenv("RSA_CORRELATOR_CLIENT_ID", f"rsa_correlator_{socket.gethostname()}")
        self.logger.info(f"[CORRELATOR_CLIENT_ID] Usando client_id persistente: {client_id}")

        try:
            self.mqtt_client = mqtt_client.Client(
                mqtt_client.CallbackAPIVersion.VERSION2,
                client_id=client_id,
                clean_session=False
            )
        except AttributeError:
            self.mqtt_client = mqtt_client.Client(client_id=client_id, clean_session=False)

        self.mqtt_client.user_data_set({"correlator": self})
        self.mqtt_client.on_connect = self._on_connect
        self.mqtt_client.on_message = self._on_message
        self.mqtt_client.on_disconnect = self._on_disconnect

        if username:
            self.mqtt_client.username_pw_set(username, password)

        # Conexión con reintento
        while self.running:
            try:
                self.logger.info(f"[MQTT_CONNECT] Conectando al broker MQTT {broker_host}:{broker_port}...")
                self.mqtt_client.connect(broker_host, broker_port, keepalive=60)
                self.mqtt_client.loop_start()
                break
            except Exception as exc:
                self.logger.warning(f"[MQTT_CONNECT_WARN] Error conectando a MQTT: {exc}. Reintentando en 5s...")
                time.sleep(5)

        # Bucle principal de mantenimiento (limpieza periódica del buffer)
        try:
            while self.running:
                time.sleep(5)
                self._limpiar_buffer_antiguo()
        finally:
            self.detener()

    def detener(self) -> None:
        if not self.running and self.mqtt_client is None:
            return
        self.running = False
        self.logger.info("[CORRELATOR_SHUTDOWN] Deteniendo servicio correlador...")
        if self.mqtt_client is not None:
            try:
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
            except Exception:
                pass
            self.mqtt_client = None
        self.logger.info("[CORRELATOR_STOP] Servicio detenido limpiamente.")

    def _handle_signal(self, signum, frame):
        sig_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
        self.logger.info(f"[SIGNAL] Señal {sig_name} recibida.")
        self.detener()
        sys.exit(0)

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self.logger.info(f"[MQTT_CONNECTED] Conectado exitosamente al broker MQTT.")
            # Suscribirse a detecciones de todas las estaciones
            client.subscribe(self.topic_sub, qos=1)
            self.logger.info(f"[MQTT_SUB] Suscrito a tópico de detecciones: {self.topic_sub}")
            # Suscribirse a respuestas de comandos para monitoreo
            client.subscribe(self.topic_res, qos=1)
            self.logger.info(f"[MQTT_SUB] Suscrito a respuestas de extracción: {self.topic_res}")
        else:
            self.logger.error(f"[MQTT_CONNECT_FAIL] Conexión rechazada con código rc={rc}")

    def _on_disconnect(self, client, userdata, flags, rc=None, properties=None):
        self.logger.warning(f"[MQTT_DISCONNECT] Desconectado del broker (rc={rc}).")

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except json.JSONDecodeError:
            self.logger.warning(f"[PAYLOAD_ERR] JSON inválido recibido en {topic}")
            return

        if "/cmd/" in topic and "/res" in topic:
            # Monitorear respuesta de extracción de alguna estación
            station_id = topic.split("/")[3]
            status = payload.get("status")
            output = payload.get("output_file", "")
            req_id = payload.get("request_id", "")
            self.logger.info(f"[STATION_RES] Estación {station_id} → status={status}, req={req_id}, archivo={output}")
            return

        if "/events/detected" in topic:
            self._procesar_deteccion_estacion(payload)

    def _procesar_deteccion_estacion(self, payload: dict) -> None:
        station_id = payload.get("station_id")
        ts_str = payload.get("timestamp")
        phase_type = payload.get("type", "P")
        probability = payload.get("probability", 0.0)

        if not station_id or not ts_str:
            self.logger.warning(f"[DETECTION_ERR] Mensaje ignorado por datos faltantes: {payload}")
            return

        try:
            dt_detection = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except ValueError as exc:
            self.logger.warning(f"[TIMESTAMP_ERR] Formato de timestamp inválido '{ts_str}': {exc}")
            return

        self.logger.info(
            f"[ALERT_RECV] Detección recibida → Estación: {station_id} | "
            f"Fase: {phase_type} (prob={probability:.4f}) | ts={ts_str}"
        )

        # 1. Filtrar ruido duplicado de la misma estación dentro de la ventana
        # Si la estación ya reportó en los últimos N segundos, actualizamos el timestamp pero no agregamos duplicado
        ahora = datetime.now(timezone.utc)
        self._limpiar_buffer_antiguo()

        # Reemplazar o agregar la detección para la estación dada
        self._actualizar_buffer(station_id, dt_detection, phase_type, probability, payload)

        # 2. Evaluar si se cumple la condición de evento regional
        self._evaluar_evento_regional(dt_detection)

    def _actualizar_buffer(self, station_id: str, dt: datetime, phase: str, prob: float, raw: dict) -> None:
        """Agrega la detección al buffer asegurando no duplicar ruido de la misma estación."""
        for item in self.buffer_detecciones:
            if item["station_id"] == station_id:
                # Si es la misma estación dentro de la ventana de coincidencia, actualizar con el evento más reciente
                dif = abs((dt - item["dt"]).total_seconds())
                if dif <= self.ventana_coincidencia_s:
                    item["dt"] = dt
                    item["type"] = phase
                    item["prob"] = prob
                    item["raw"] = raw
                    return

        # Si es una nueva estación en la ventana, la agregamos
        self.buffer_detecciones.append({
            "station_id": station_id,
            "dt": dt,
            "type": phase,
            "prob": prob,
            "raw": raw
        })

    def _limpiar_buffer_antiguo(self) -> None:
        """Elimina del buffer las detecciones más antiguas que el doble de la ventana de coincidencia."""
        ahora = datetime.now(timezone.utc)
        max_age = max(30.0, self.ventana_coincidencia_s * 2.0)
        self.buffer_detecciones = [
            d for d in self.buffer_detecciones
            if (ahora - d["dt"]).total_seconds() <= max_age
        ]

    def _evaluar_evento_regional(self, dt_referencia: datetime) -> None:
        """Verifica si existen >= min_estaciones distintas dentro de la ventana temporal."""
        ahora_sec = time.time()
        cooldown_restante = (self.last_broadcast_time + self.cooldown_evento_s) - ahora_sec
        if cooldown_restante > 0:
            self.logger.debug(f"[COOLDOWN_ACTIVE] Coincidencia detectada pero correlador en cooldown ({cooldown_restante:.1f}s restantes).")
            return

        # Buscar detecciones dentro del rango [dt_referencia - ventana, dt_referencia + ventana]
        detecciones_coincidentes = []
        estaciones_unicas = set()

        for d in self.buffer_detecciones:
            delta = abs((d["dt"] - dt_referencia).total_seconds())
            if delta <= self.ventana_coincidencia_s:
                detecciones_coincidentes.append(d)
                estaciones_unicas.add(d["station_id"])

        if len(estaciones_unicas) >= self.min_estaciones:
            # ¡EVENTO REGIONAL CONFIRMADO!
            self.logger.info(
                f"[EVENTO_REGIONAL_CONFIRMADO] 🚨 Coincidencia detectada en {len(estaciones_unicas)} estaciones "
                f"({', '.join(sorted(estaciones_unicas))}) dentro de ventana de {self.ventana_coincidencia_s}s!"
            )
            self._disparar_extraccion_broadcast(detecciones_coincidentes, list(estaciones_unicas))
            self.last_broadcast_time = ahora_sec
            self.buffer_detecciones.clear()  # Limpiar buffer tras confirmar evento

    def _disparar_extraccion_broadcast(self, detecciones: List[dict], estaciones: List[str]) -> None:
        """Calcula el rango temporal y publica la orden de extracción broadcast en MQTT."""
        # Encontrar la fecha de inicio más temprana entre las detecciones coincidentes
        dt_min = min(d["dt"] for d in detecciones)
        dt_start = dt_min - timedelta(seconds=self.ventana_pre_evento_s)
        start_str = dt_start.strftime("%Y-%m-%dZ%H:%M:%S.%f")[:-3]
        duration = float(self.ventana_pre_evento_s + self.ventana_post_evento_s)

        req_id = f"corr-{dt_min.strftime('%Y%m%d-%H%M%S')}"

        cmd_payload = {
            "start": start_str,
            "duration": duration,
            "upload": True,
            "delete_after_upload": self.delete_after_upload,
            "request_id": req_id,
            "source": "regional_correlator",
            "participating_stations": estaciones
        }

        json_payload = json.dumps(cmd_payload, ensure_ascii=False)
        self.logger.info(
            f"[BROADCAST_SEND] Publicando orden de extracción masiva en '{self.topic_broadcast}' → "
            f"req_id={req_id}, start={start_str}, duration={duration}s, "
            f"delete_after_upload={self.delete_after_upload}, estaciones={estaciones}"
        )

        try:
            res = self.mqtt_client.publish(self.topic_broadcast, json_payload, qos=1, retain=False)
            if res.rc == 0:
                self.logger.info(f"[BROADCAST_OK] Comando publicado exitosamente (mid={res.mid}).")
            else:
                self.logger.error(f"[BROADCAST_FAIL] Fallo al publicar comando broadcast (rc={res.rc}).")
        except Exception as exc:
            self.logger.error(f"[BROADCAST_ERR] Excepción enviando comando MQTT: {exc}")

        # Construir y publicar payload de metadatos para InfluxDB / Telegraf
        estaciones_sorted = sorted(estaciones)
        stations_csv = ",".join(estaciones_sorted)
        trigger_details = {
            "window_s": self.ventana_coincidencia_s,
            "detections": [
                {
                    "station": d["station_id"],
                    "phase": d["type"],
                    "probability": d["prob"],
                    "timestamp": d["dt"].strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
                }
                for d in detecciones
            ]
        }

        # Timestamp UTC de referencia del evento
        evt_timestamp_str = dt_min.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        meta_payload = {
            "event_type": "auto",
            "source": "correlator",
            "event_id": req_id,
            "timestamp_utc": evt_timestamp_str,
            "stations": stations_csv,
            "n_stations": len(estaciones),
            "duration_s": duration,
            "request_id": req_id,
            "details": json.dumps(trigger_details, ensure_ascii=False)
        }

        meta_json = json.dumps(meta_payload, ensure_ascii=False)
        self.logger.info(
            f"[METADATA_SEND] Publicando metadatos de evento en '{self.topic_metadata}' → "
            f"event_id={req_id}, stations={stations_csv}, n={len(estaciones)}"
        )

        try:
            res_meta = self.mqtt_client.publish(self.topic_metadata, meta_json, qos=1, retain=False)
            if res_meta.rc == 0:
                self.logger.info(f"[METADATA_OK] Metadatos publicados exitosamente (mid={res_meta.mid}).")
            else:
                self.logger.error(f"[METADATA_FAIL] Fallo al publicar metadatos (rc={res_meta.rc}).")
        except Exception as exc:
            self.logger.error(f"[METADATA_ERR] Excepción enviando metadatos MQTT: {exc}")


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "config.json")
    env_path = os.path.join(script_dir, ".env")

    if os.path.exists(env_path):
        load_dotenv(env_path)

    # Configurar logger a consola (stdout)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    logger = logging.getLogger("regional_correlator")

    correlator = RegionalEventCorrelator(config_path, logger)
    correlator.iniciar()


if __name__ == "__main__":
    main()
