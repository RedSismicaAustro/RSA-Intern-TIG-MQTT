#!/usr/bin/env python3
"""
fix_event_ids.py — Migración retroactiva de identificadores de eventos en InfluxDB (ADR-016 / Paso 4)

Este script:
1. Conecta al bucket de eventos sísmicos en InfluxDB v2.
2. Consulta todos los eventos registrados con prefijo 'corr-'.
3. Compara el sufijo temporal del 'event_id' contra el timestamp original '_time'.
4. Si difieren (desfase temporal), elimina el registro desfasado y lo reescribe con
   el 'event_id' exacto calculado a partir de '_time' (corr-YYYYMMDD-HHMMSS), preservando
   todos los tags, fields y detalles JSON intactos.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

try:
    from dotenv import load_dotenv
    _DOTENV_AVAILABLE = True
except ImportError:
    _DOTENV_AVAILABLE = False

try:
    import influxdb_client
    from influxdb_client.client.write_api import SYNCHRONOUS
    from influxdb_client import Point
    _INFLUX_AVAILABLE = True
except ImportError:
    _INFLUX_AVAILABLE = False


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    return logging.getLogger("fix_event_ids")


def load_environment():
    """Intenta cargar variables de entorno desde posibles ubicaciones de .env."""
    if _DOTENV_AVAILABLE:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        possible_envs = [
            os.path.join(script_dir, ".env"),
            os.path.join(script_dir, "..", "correlator", ".env"),
            os.path.join(script_dir, "..", "..", "services", "docker-unified", ".env"),
        ]
        for env_file in possible_envs:
            if os.path.exists(env_file):
                load_dotenv(env_file)
                break


def parse_args():
    parser = argparse.ArgumentParser(
        description="Migración retroactiva de event_id en InfluxDB para alinear con timestamp real (_time)"
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("INFLUXDB_URL", "http://localhost:8086"),
        help="URL de InfluxDB (defecto: $INFLUXDB_URL o http://localhost:8086)"
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("INFLUXDB_TOKEN", ""),
        help="Token de autenticación InfluxDB (defecto: $INFLUXDB_TOKEN)"
    )
    parser.add_argument(
        "--org",
        default=os.environ.get("INFLUXDB_ORG", "rsa"),
        help="Organización de InfluxDB (defecto: $INFLUXDB_ORG o 'rsa')"
    )
    parser.add_argument(
        "--bucket",
        default=os.environ.get("INFLUXDB_EVENTS_BUCKET", "rsa_events"),
        help="Bucket de eventos (defecto: $INFLUXDB_EVENTS_BUCKET o 'rsa_events')"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Modo simulación: muestra los cambios sin modificar la base de datos."
    )
    return parser.parse_args()


def migrate_event_ids(logger: logging.Logger, args: argparse.Namespace):
    if not _INFLUX_AVAILABLE:
        logger.error("La librería 'influxdb-client' no está instalada. Ejecuta: pip install influxdb-client")
        sys.exit(1)

    if not args.token:
        logger.error("No se especificó un token de InfluxDB. Usa --token o define $INFLUXDB_TOKEN.")
        sys.exit(1)

    logger.info(f"Conectando a InfluxDB en {args.url} (Org: {args.org}, Bucket: {args.bucket})...")
    if args.dry_run:
        logger.info("⚡ [MODO DRY-RUN] No se realizarán escrituras ni borrados.")

    client = influxdb_client.InfluxDBClient(
        url=args.url,
        token=args.token,
        org=args.org,
        timeout=30_000
    )

    if not client.ping():
        logger.error("No se pudo establecer conexión con InfluxDB. Verifica que el servicio esté corriendo y la URL sea accesible.")
        sys.exit(1)

    logger.info("✅ Conexión con InfluxDB exitosa.")

    query_api = client.query_api()
    write_api = client.write_api(write_options=SYNCHRONOUS)
    delete_api = client.delete_api()

    # Consultar todos los eventos registrados
    query = f'''
    from(bucket: "{args.bucket}")
        |> range(start: 1970-01-01T00:00:00Z)
        |> filter(fn: (r) => r._measurement == "seismic_event")
        |> pivot(rowKey: ["_time", "event_id"], columnKey: ["_field"], valueColumn: "_value")
    '''

    logger.info("Consultando catálogo de eventos en InfluxDB...")
    try:
        tables = query_api.query(query, org=args.org)
    except Exception as exc:
        logger.error(f"Error al consultar InfluxDB: {exc}")
        sys.exit(1)

    total_events = 0
    migrated_count = 0
    already_correct_count = 0
    skipped_count = 0

    migration_plan: List[Dict[str, Any]] = []

    for table in tables:
        for record in table.records:
            total_events += 1
            vals = record.values
            old_event_id = vals.get("event_id", "")
            record_time = record.get_time()

            if not old_event_id or not record_time:
                skipped_count += 1
                continue

            # Solo migrar eventos automáticos generados por el correlador (corr-*)
            if not old_event_id.startswith("corr-"):
                logger.debug(f"[SKIP] Evento no-correlador ignorado: {old_event_id}")
                skipped_count += 1
                continue

            # Calcular nuevo event_id determinista a partir de _time
            expected_id = f"corr-{record_time.strftime('%Y%m%d-%H%M%S')}"

            if old_event_id == expected_id:
                already_correct_count += 1
                logger.info(f"[OK] {old_event_id} coincide exactamente con _time ({record_time.isoformat()})")
            else:
                migration_plan.append({
                    "old_id": old_event_id,
                    "new_id": expected_id,
                    "time": record_time,
                    "event_type": vals.get("event_type", "auto"),
                    "source": vals.get("source", "correlator"),
                    "stations": str(vals.get("stations", "")),
                    "n_stations": int(vals.get("n_stations", 0)),
                    "duration_s": float(vals.get("duration_s", 120.0)),
                    "request_id": expected_id if vals.get("request_id", "").startswith("corr-") else vals.get("request_id", expected_id),
                    "details": str(vals.get("details", "{}"))
                })

    logger.info("=" * 60)
    logger.info(f"RESUMEN DE ANÁLISIS:")
    logger.info(f"  - Total de eventos leídos: {total_events}")
    logger.info(f"  - Ya correctos: {already_correct_count}")
    logger.info(f"  - Ignorados (no corr-*): {skipped_count}")
    logger.info(f"  - Requieren migración: {len(migration_plan)}")
    logger.info("=" * 60)

    if not migration_plan:
        logger.info("🎉 Todos los eventos correlados ya tienen IDs temporales coherentes. Nada que migrar.")
        return

    # Ejecutar migración
    for item in migration_plan:
        old_id = item["old_id"]
        new_id = item["new_id"]
        rec_time = item["time"]

        logger.info(f"🔄 Migrando: {old_id}  ➜  {new_id}  (_time={rec_time.isoformat()})")

        if not args.dry_run:
            try:
                # 1. Crear nuevo punto con el event_id corregido
                p = (
                    Point("seismic_event")
                    .tag("event_id", new_id)
                    .tag("event_type", item["event_type"])
                    .tag("source", item["source"])
                    .field("stations", item["stations"])
                    .field("n_stations", item["n_stations"])
                    .field("duration_s", item["duration_s"])
                    .field("request_id", item["request_id"])
                    .field("details", item["details"])
                    .time(rec_time)
                )
                write_api.write(bucket=args.bucket, org=args.org, record=p)

                # 2. Eliminar punto desfasado original usando rango temporal estrecho y predicado
                del_start = rec_time - timedelta(seconds=1)
                del_stop = rec_time + timedelta(seconds=1)
                del_predicate = f'_measurement="seismic_event" AND event_id="{old_id}"'
                
                delete_api.delete(
                    start=del_start,
                    stop=del_stop,
                    predicate=del_predicate,
                    bucket=args.bucket,
                    org=args.org
                )

                migrated_count += 1
            except Exception as exc:
                logger.error(f"❌ Error migrando evento {old_id}: {exc}")
        else:
            migrated_count += 1

    if args.dry_run:
        logger.info(f"⚡ [DRY-RUN] Se habrían migrado {migrated_count} eventos.")
    else:
        logger.info(f"✅ Migración completada exitosamente: {migrated_count} eventos actualizados.")


def main():
    logger = setup_logging()
    load_environment()
    args = parse_args()
    migrate_event_ids(logger, args)


if __name__ == "__main__":
    main()
