#!/usr/bin/env python3
"""
mqtt_notify.py — Notificador MQTT para operaciones de Respaldo y Sincronización.

Publica telemetría JSON de las operaciones de respaldo al broker MQTT
en el tópico rsa/seismic/smart/system/backup con QoS 1.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Intentar cargar .env si existe en rutas relativas comunes
try:
    from dotenv import load_dotenv
    for env_candidate in [
        Path(__file__).resolve().parent / ".env",
        Path(__file__).resolve().parent.parent.parent / "services" / "docker-unified" / ".env",
        Path("/app/.env")
    ]:
        if env_candidate.exists():
            load_dotenv(env_candidate)
            break
except ImportError:
    pass

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("[ERROR] paho-mqtt no está instalado.", file=sys.stderr)
    sys.exit(1)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publica telemetría del estado de respaldo InfluxDB a MQTT."
    )
    parser.add_argument(
        "--status",
        type=str,
        choices=["success", "failure"],
        required=True,
        help="Resultado de la operación de respaldo (success o failure)."
    )
    parser.add_argument(
        "--events-count",
        type=int,
        default=0,
        help="Cantidad de eventos exportados/respaldados."
    )
    parser.add_argument(
        "--snapshot-size",
        type=int,
        default=0,
        help="Tamaño en bytes del archivo comprimido de snapshot binario."
    )
    parser.add_argument(
        "--csv-size",
        type=int,
        default=0,
        help="Tamaño en bytes del archivo CSV exportado."
    )
    parser.add_argument(
        "--backup-file",
        type=str,
        default=None,
        help="Nombre del archivo de respaldo generado (ej. rsa_events_YYYY-MM-DD.tar.gz)."
    )
    parser.add_argument(
        "--drive-path",
        type=str,
        default="RSA-Backups/influxdb/",
        help="Ruta destino en Google Drive (default: RSA-Backups/influxdb/)."
    )
    parser.add_argument(
        "--purged-count",
        type=int,
        default=0,
        help="Cantidad de respaldos antiguos purgados por rotación."
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="Duración total de la operación en segundos."
    )
    parser.add_argument(
        "--error-message",
        type=str,
        default=None,
        help="Descripción del error en caso de fallo."
    )
    parser.add_argument(
        "--server",
        type=str,
        default=None,
        help="Identificador del servidor (default: TELEGRAF_CLIENT_ID o hostname)."
    )
    parser.add_argument(
        "--topic",
        type=str,
        default=None,
        help="Tópico MQTT destino (default: rsa/seismic/smart/system/backup)."
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    # Resolver parámetros de entorno / CLI
    server_id = (
        args.server
        or os.getenv("TELEGRAF_CLIENT_ID")
        or os.getenv("HOSTNAME")
        or "events-server"
    )
    topic = (
        args.topic
        or os.getenv("MQTT_BACKUP_TOPIC")
        or "rsa/seismic/smart/system/backup"
    )

    broker_host = os.getenv("MQTT_BROKER", "localhost")
    broker_port = int(os.getenv("MQTT_PORT", "1883"))
    username = os.getenv("MQTT_USERNAME")
    password = os.getenv("MQTT_PASSWORD")

    timestamp_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    payload = {
        "source": "backup_events",
        "server": server_id,
        "status": args.status,
        "timestamp_utc": timestamp_utc,
        "snapshot_size_bytes": args.snapshot_size,
        "csv_size_bytes": args.csv_size,
        "events_count": args.events_count,
        "backup_file": args.backup_file,
        "drive_path": args.drive_path,
        "purged_count": args.purged_count,
        "duration_s": round(args.duration, 2),
        "error_message": args.error_message,
    }

    payload_json = json.dumps(payload, ensure_ascii=False)

    print(f"[MQTT_NOTIFY] Preparando notificación:")
    print(f"  - Servidor  : {server_id}")
    print(f"  - Estado    : {args.status}")
    print(f"  - Broker    : {broker_host}:{broker_port}")
    print(f"  - Tópico    : {topic}")
    print(f"  - Payload   : {payload_json}")

    # Inicializar cliente MQTT con compatibilidad paho v1 y v2
    client_id = f"backup-notify-{int(time.time())}"
    try:
        # Paho MQTT v2+
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv311
        )
    except AttributeError:
        # Paho MQTT v1
        client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)

    if username and password:
        client.username_pw_set(username=username, password=password)

    try:
        client.connect(broker_host, broker_port, keepalive=30)
        client.loop_start()

        msg_info = client.publish(topic, payload_json, qos=1)
        msg_info.wait_for_publish(timeout=10.0)

        if not msg_info.is_published():
            print(f"[MQTT_NOTIFY_ERROR] Timeout esperando confirmación de publicación (QoS 1).", file=sys.stderr)
            sys.exit(1)

        print(f"[MQTT_NOTIFY_SUCCESS] Notificación publicada exitosamente al tópico '{topic}'.")
    except Exception as exc:
        print(f"[MQTT_NOTIFY_ERROR] Error publicando a MQTT: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    main()
