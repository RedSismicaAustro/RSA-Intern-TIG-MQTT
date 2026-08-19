import json
import logging
import os
import socket
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    import influxdb_client
    _INFLUX_AVAILABLE = True
except ImportError:
    _INFLUX_AVAILABLE = False

try:
    import paho.mqtt.client as mqtt_client
    _MQTT_AVAILABLE = True
except ImportError:
    _MQTT_AVAILABLE = False

logger = logging.getLogger(__name__)


class InfluxEventsClient:
    """Cliente para consulta de eventos en InfluxDB y publicación de clasificación MQTT."""

    def __init__(self):
        self.url = os.environ.get("INFLUXDB_URL", "http://influxdb:8086")
        self.token = os.environ.get("INFLUXDB_TOKEN", "")
        self.org = os.environ.get("INFLUXDB_ORG", "rsa")
        self.bucket = os.environ.get("INFLUXDB_EVENTS_BUCKET", "rsa_events")

        self.mqtt_broker = os.environ.get("MQTT_BROKER", "localhost")
        self.mqtt_port = int(os.environ.get("MQTT_PORT", 1883))
        self.mqtt_user = os.environ.get("MQTT_USERNAME", "")
        self.mqtt_pass = os.environ.get("MQTT_PASSWORD", "")
        self.mqtt_topic = os.environ.get("MQTT_METADATA_TOPIC", "rsa/seismic/smart/events/metadata")

        self._client = None
        if _INFLUX_AVAILABLE and self.token:
            try:
                self._client = influxdb_client.InfluxDBClient(
                    url=self.url,
                    token=self.token,
                    org=self.org,
                    timeout=10_000
                )
            except Exception as exc:
                logger.error(f"[INFLUX_INIT_ERR] Error inicializando cliente InfluxDB: {exc}")

    def ping(self) -> bool:
        """Comprueba conectividad con InfluxDB."""
        if not self._client:
            return False
        try:
            return self._client.ping()
        except Exception as exc:
            logger.warning(f"[INFLUX_PING_FAIL] Error conectando a InfluxDB: {exc}")
            return False

    def get_recorded_dates(self) -> List[date]:
        """Obtiene la lista de fechas únicas (UTC) que contienen eventos registrados."""
        if not self._client:
            return []

        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: 0)
            |> filter(fn: (r) => r._measurement == "seismic_event" and r._field == "stations")
            |> keep(columns: ["_time"])
        '''
        try:
            query_api = self._client.query_api()
            tables = query_api.query(query, org=self.org)
            dates_set = set()
            for table in tables:
                for record in table.records:
                    dt = record.get_time()
                    if dt:
                        dates_set.add(dt.date())
            return sorted(list(dates_set))
        except Exception as exc:
            logger.error(f"[INFLUX_QUERY_DATES_ERR] Error consultando fechas de eventos: {exc}")
            return []

    def get_events_by_date(self, target_date: date) -> List[Dict[str, Any]]:
        """
        Consulta todos los eventos sísmicos ocurridos en una fecha (UTC).
        Prioriza clasificaciones manuales/confirmadas sobre automáticas.
        """
        if not self._client:
            return []

        start_dt = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
        stop_dt = start_dt + timedelta(days=1)
        start_str = start_dt.isoformat()
        stop_str = stop_dt.isoformat()

        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: {start_str}, stop: {stop_str})
            |> filter(fn: (r) => r._measurement == "seismic_event")
            |> pivot(rowKey: ["_time", "event_id"], columnKey: ["_field"], valueColumn: "_value")
        '''

        # Jerarquía de prioridad de estados
        PRIORITY = {
            "confirmed": 3,
            "discarded": 3,
            "manual": 2,
            "auto": 1
        }

        try:
            query_api = self._client.query_api()
            tables = query_api.query(query, org=self.org)

            events_by_id: Dict[str, Dict[str, Any]] = {}

            for table in tables:
                for record in table.records:
                    values = record.values
                    evt_id = values.get("event_id")
                    if not evt_id:
                        continue

                    # Parsear stations
                    stations_raw = values.get("stations", "")
                    if isinstance(stations_raw, str):
                        stations_list = [s.strip() for s in stations_raw.split(",") if s.strip()]
                    elif isinstance(stations_raw, list):
                        stations_list = stations_raw
                    else:
                        stations_list = []

                    record_dt = record.get_time()

                    # Parsear details
                    details_raw = values.get("details", "{}")
                    details_obj = {}
                    if isinstance(details_raw, str):
                        try:
                            details_obj = json.loads(details_raw)
                        except Exception:
                            details_obj = {}
                    elif isinstance(details_raw, dict):
                        details_obj = details_raw

                    evt_type = values.get("event_type", "auto")

                    event_entry = {
                        "event_id": evt_id,
                        "event_type": evt_type,
                        "source": values.get("source", "correlator"),
                        "reference_time_utc": record_dt,
                        "timestamp_utc": record_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z" if record_dt else "",
                        "stations": stations_list,
                        "stations_str": ",".join(stations_list),
                        "n_stations": int(values.get("n_stations", len(stations_list))),
                        "duration_s": float(values.get("duration_s", 120.0)),
                        "request_id": values.get("request_id", evt_id),
                        "details": details_obj,
                        "raw_details_str": details_raw if isinstance(details_raw, str) else json.dumps(details_obj),
                        "_time": record_dt
                    }

                    if evt_id in events_by_id:
                        prev_priority = PRIORITY.get(events_by_id[evt_id]["event_type"], 0)
                        curr_priority = PRIORITY.get(evt_type, 0)
                        if curr_priority >= prev_priority:
                            events_by_id[evt_id] = event_entry
                    else:
                        events_by_id[evt_id] = event_entry

            event_list = list(events_by_id.values())
            event_list.sort(key=lambda x: x["reference_time_utc"] or datetime.min.replace(tzinfo=timezone.utc))
            return event_list

        except Exception as exc:
            logger.error(f"[INFLUX_QUERY_EVENTS_ERR] Error consultando eventos para {target_date}: {exc}")
            return []

    def publish_classification(
        self,
        event_id: str,
        new_type: str,
        current_event: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        Publica una actualización de clasificación (confirmed | discarded) al broker MQTT
        usando el timestamp UTC original del evento para mantener la sincronización temporal.
        """
        if not _MQTT_AVAILABLE:
            return False, "Librería paho-mqtt no disponible en el contenedor."

        client_suffix = uuid.uuid4().hex[:6]
        client_id = f"rsa_event_analyzer_{socket.gethostname()}_{client_suffix}"

        try:
            try:
                mqtt_c = mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION2, client_id=client_id)
            except AttributeError:
                mqtt_c = mqtt_client.Client(client_id=client_id)

            if self.mqtt_user:
                mqtt_c.username_pw_set(self.mqtt_user, self.mqtt_pass)

            mqtt_c.connect(self.mqtt_broker, self.mqtt_port, keepalive=30)
            mqtt_c.loop_start()

            # Timestamp de referencia original del evento
            ref_dt = current_event.get("reference_time_utc")
            if isinstance(ref_dt, datetime):
                ts_utc = ref_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            elif current_event.get("timestamp_utc"):
                ts_utc = str(current_event["timestamp_utc"])
            else:
                ts_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

            stations_csv = current_event.get("stations_str", "")
            if not stations_csv and isinstance(current_event.get("stations"), list):
                stations_csv = ",".join(current_event["stations"])

            payload = {
                "event_type": new_type,
                "source": "event_analyzer",
                "event_id": event_id,
                "timestamp_utc": ts_utc,
                "stations": stations_csv,
                "n_stations": int(current_event.get("n_stations", len(stations_csv.split(",")))),
                "duration_s": float(current_event.get("duration_s", 120.0)),
                "request_id": str(current_event.get("request_id", event_id)),
                "details": current_event.get("raw_details_str", "{}")
            }

            json_msg = json.dumps(payload, ensure_ascii=False)
            res = mqtt_c.publish(self.mqtt_topic, json_msg, qos=1, retain=False)
            res.wait_for_publish(timeout=5.0)

            mqtt_c.loop_stop()
            mqtt_c.disconnect()

            logger.info(f"[CLASSIFICATION_PUB_OK] Evento {event_id} clasificado como '{new_type}' emitido a MQTT.")
            return True, "Clasificación publicada exitosamente a la red RSA."

        except Exception as exc:
            logger.error(f"[CLASSIFICATION_PUB_ERR] Error publicando clasificación MQTT: {exc}")
            return False, str(exc)
