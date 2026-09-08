#!/usr/bin/env python3
"""
migrate_stations.py — Migración y Renombrado de Estaciones en InfluxDB v2 (RSA)

Este script permite renombrar estaciones históricas en los buckets 'telemetry' y 'rsa_events':
  - DEV01  -> TEST
  - TEN01  -> TENG
  - TEN1   -> TENG

Estrategia:
1. En bucket 'telemetry':
   - Detecta la política de retención (ej. 90d) para evitar rechazos por puntos expirados.
   - Consulta todas las series temporales vigentes asociadas al tag 'station_id'.
   - Reescribe los puntos con el nuevo 'station_id', preservando timestamps, tags y fields.
   - Purgar los registros del tag antiguo mediante la API de borrado de InfluxDB v2.
2. En bucket 'rsa_events':
   - Consulta el catálogo de eventos sísmicos ('seismic_event').
   - Si los campos 'stations' o 'details' contienen referencias a las estaciones anteriores,
     los actualiza y reescribe.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

try:
    from dotenv import load_dotenv
    _DOTENV_AVAILABLE = True
except ImportError:
    _DOTENV_AVAILABLE = False

try:
    import influxdb_client
    from influxdb_client.client.write_api import SYNCHRONOUS
    from influxdb_client.rest import ApiException
    from influxdb_client import Point
    _INFLUX_AVAILABLE = True
except ImportError:
    _INFLUX_AVAILABLE = False


STATION_MAPPINGS = {
    "DEV01": "TEST",
    "TEN01": "TENG",
    "TEN1":  "TENG"
}

RESERVED_FLUX_KEYS = {
    "result", "table", "_start", "_stop", "_time", "_measurement", "_field", "_value"
}


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    return logging.getLogger("migrate_stations")


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
        description="Migración y renombrado de estaciones en InfluxDB v2 (telemetry y rsa_events)"
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
        "--telemetry-bucket",
        default=os.environ.get("INFLUXDB_BUCKET", "telemetry"),
        help="Bucket de telemetría (defecto: $INFLUXDB_BUCKET o 'telemetry')"
    )
    parser.add_argument(
        "--events-bucket",
        default=os.environ.get("INFLUXDB_EVENTS_BUCKET", "rsa_events"),
        help="Bucket de eventos (defecto: $INFLUXDB_EVENTS_BUCKET o 'rsa_events')"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=2000,
        help="Tamaño de lote para escrituras (defecto: 2000)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Modo simulación: muestra los conteos y acciones sin escribir ni borrar datos."
    )
    return parser.parse_args()


def get_retention_cutoff(
    client: "influxdb_client.InfluxDBClient",
    logger: logging.Logger,
    org: str,
    bucket_name: str
) -> Optional[datetime]:
    """Determina el límite inferior de retención para evitar error 422 en escrituras."""
    try:
        buckets_api = client.buckets_api()
        bucket = buckets_api.find_bucket_by_name(bucket_name)
        if bucket and bucket.retention_rules:
            for rule in bucket.retention_rules:
                if rule.every_seconds > 0:
                    # Añadir 5 minutos de margen de seguridad
                    margin_seconds = rule.every_seconds - 300
                    cutoff = datetime.now(timezone.utc) - timedelta(seconds=margin_seconds)
                    logger.info(f"Bucket '{bucket_name}' retención detectada: {rule.every_seconds // 86400} días. Límite de corte: {cutoff.isoformat()}")
                    return cutoff
    except Exception as exc:
        logger.warning(f"No se pudo consultar la retención del bucket '{bucket_name}': {exc}")

    # Por defecto para telemetry usamos 89 días de corte
    cutoff = datetime.now(timezone.utc) - timedelta(days=89, hours=20)
    logger.info(f"Usando corte de retención por defecto (89 días): {cutoff.isoformat()}")
    return cutoff


def safe_write_batch(
    write_api,
    bucket: str,
    org: str,
    points: List[Point],
    logger: logging.Logger
) -> int:
    """Escribe un lote de puntos de forma segura; si falla, intenta escribir individualmente."""
    if not points:
        return 0

    try:
        write_api.write(bucket=bucket, org=org, record=points)
        return len(points)
    except ApiException as api_exc:
        logger.warning(f"Error en lote ({api_exc.status}): intentando reintentar individualmente...")
        written = 0
        for p in points:
            try:
                write_api.write(bucket=bucket, org=org, record=p)
                written += 1
            except Exception as single_exc:
                logger.debug(f"Punto descartado por límite de retención: {single_exc}")
        return written
    except Exception as exc:
        logger.error(f"Error escribiendo lote en '{bucket}': {exc}")
        return 0


def migrate_telemetry_station(
    client: "influxdb_client.InfluxDBClient",
    logger: logging.Logger,
    org: str,
    bucket: str,
    old_station: str,
    new_station: str,
    batch_size: int,
    cutoff_time: Optional[datetime],
    dry_run: bool
) -> int:
    """Migra todas las series de una estación en el bucket de telemetría."""
    query_api = client.query_api()
    write_api = client.write_api(write_options=SYNCHRONOUS)
    delete_api = client.delete_api()

    logger.info(f"--- [TELEMETRY] Procesando migración: {old_station} -> {new_station} ---")

    # Si hay corte de retención, filtrar desde esa fecha para no transferir datos expirados
    start_str = cutoff_time.strftime("%Y-%m-%dT%H:%M:%SZ") if cutoff_time else "1970-01-01T00:00:00Z"

    query = f'''
    from(bucket: "{bucket}")
        |> range(start: {start_str})
        |> filter(fn: (r) => r.station_id == "{old_station}")
    '''

    try:
        tables = query_api.query(query, org=org)
    except Exception as exc:
        logger.error(f"Error consultando puntos para estación {old_station}: {exc}")
        return 0

    points_to_write: List[Point] = []
    total_records = 0
    written_records = 0
    dropped_expired = 0

    for table in tables:
        for record in table.records:
            total_records += 1
            record_time = record.get_time()

            # Validación de retención
            if cutoff_time and record_time and record_time < cutoff_time:
                dropped_expired += 1
                continue

            measurement = record.get_measurement()
            field_name = record.get_field()
            field_value = record.get_value()

            p = Point(measurement).time(record_time)

            # Copiar tags reemplazando station_id
            for key, val in record.values.items():
                if key in RESERVED_FLUX_KEYS:
                    continue
                if key == "station_id":
                    p.tag("station_id", new_station)
                else:
                    if val is not None:
                        p.tag(key, str(val))

            p.field(field_name, field_value)
            points_to_write.append(p)

            if len(points_to_write) >= batch_size:
                if not dry_run:
                    w = safe_write_batch(write_api, bucket, org, points_to_write, logger)
                    written_records += w
                else:
                    written_records += len(points_to_write)
                logger.info(f"  -> Procesados {written_records} puntos de {old_station}...")
                points_to_write.clear()

    # Escribir remanentes
    if points_to_write:
        if not dry_run:
            w = safe_write_batch(write_api, bucket, org, points_to_write, logger)
            written_records += w
        else:
            written_records += len(points_to_write)
        points_to_write.clear()

    if dropped_expired > 0:
        logger.info(f"  ℹ️ Puntos ignorados por haber expirado según política de retención: {dropped_expired}")

    logger.info(f"  Total de puntos vigentes procesados para '{old_station}': {written_records}")

    if written_records > 0 or total_records > 0:
        if dry_run:
            logger.info(f"  ⚡ [DRY-RUN] Se habrían reescrito {written_records} puntos como '{new_station}' y purgado '{old_station}'.")
        else:
            logger.info(f"  🗑️ Purgando serie antigua '{old_station}' en bucket '{bucket}'...")
            try:
                delete_api.delete(
                    start="1970-01-01T00:00:00Z",
                    stop="2030-01-01T00:00:00Z",
                    predicate=f'station_id="{old_station}"',
                    bucket=bucket,
                    org=org
                )
                logger.info(f"  ✅ Migración y purga completada para {old_station} -> {new_station}.")
            except Exception as exc:
                logger.error(f"  ❌ Error eliminando serie antigua {old_station}: {exc}")
    else:
        logger.info(f"  ℹ️ No se encontraron registros para '{old_station}' en bucket '{bucket}'.")

    return written_records


def migrate_events_catalog(
    client: "influxdb_client.InfluxDBClient",
    logger: logging.Logger,
    org: str,
    bucket: str,
    dry_run: bool
) -> int:
    """Actualiza referencias a estaciones antiguas en el bucket de eventos rsa_events."""
    query_api = client.query_api()
    write_api = client.write_api(write_options=SYNCHRONOUS)

    logger.info(f"--- [EVENTS] Verificando referencias en catálogo '{bucket}' ---")

    query = f'''
    from(bucket: "{bucket}")
        |> range(start: 1970-01-01T00:00:00Z)
        |> filter(fn: (r) => r._measurement == "seismic_event")
        |> pivot(rowKey: ["_time", "event_id"], columnKey: ["_field"], valueColumn: "_value")
    '''

    try:
        tables = query_api.query(query, org=org)
    except Exception as exc:
        logger.warning(f"No se pudo consultar bucket de eventos '{bucket}': {exc}")
        return 0

    events_to_update: List[Point] = []
    updated_count = 0

    for table in tables:
        for record in table.records:
            vals = record.values
            stations_str = str(vals.get("stations", ""))
            details_str = str(vals.get("details", "{}"))
            event_id = str(vals.get("event_id", ""))
            record_time = record.get_time()

            needs_update = False
            new_stations = stations_str
            new_details = details_str

            for old_st, new_st in STATION_MAPPINGS.items():
                # Reemplazo en string stations (ej. DEV01,CHA2 -> TEST,CHA2)
                st_list = [s.strip() for s in new_stations.split(",") if s.strip()]
                if old_st in st_list:
                    st_list = [new_st if s == old_st else s for s in st_list]
                    # Eliminar duplicados manteniendo orden
                    deduped = []
                    for s in st_list:
                        if s not in deduped:
                            deduped.append(s)
                    new_stations = ",".join(deduped)
                    needs_update = True

                # Reemplazo en JSON details si aplica
                if f'"{old_st}"' in new_details:
                    new_details = new_details.replace(f'"{old_st}"', f'"{new_st}"')
                    needs_update = True

            if needs_update:
                updated_count += 1
                logger.info(f"  🔄 Evento {event_id} ({record_time.isoformat()}): '{stations_str}' -> '{new_stations}'")

                n_stations = len([s for s in new_stations.split(",") if s.strip()])
                p = (
                    Point("seismic_event")
                    .tag("event_id", event_id)
                    .tag("event_type", str(vals.get("event_type", "auto")))
                    .tag("source", str(vals.get("source", "correlator")))
                    .field("stations", new_stations)
                    .field("n_stations", n_stations)
                    .field("duration_s", float(vals.get("duration_s", 120.0)))
                    .field("request_id", str(vals.get("request_id", event_id)))
                    .field("details", new_details)
                    .time(record_time)
                )
                events_to_update.append(p)

    if events_to_update and not dry_run:
        write_api.write(bucket=bucket, org=org, record=events_to_update)
        logger.info(f"  ✅ {len(events_to_update)} eventos actualizados exitosamente en '{bucket}'.")
    elif dry_run:
        logger.info(f"  ⚡ [DRY-RUN] Se habrían actualizado {updated_count} eventos en '{bucket}'.")
    else:
        logger.info(f"  ℹ️ Ningún evento requirió actualización de nombres de estación.")

    return updated_count


def main():
    logger = setup_logging()
    load_environment()
    args = parse_args()

    if not _INFLUX_AVAILABLE:
        logger.error("La librería 'influxdb-client' no está disponible.")
        sys.exit(1)

    if not args.token:
        logger.error("No se especificó token de InfluxDB. Usa --token o define $INFLUXDB_TOKEN.")
        sys.exit(1)

    logger.info("=" * 65)
    logger.info("MIGRACIÓN Y RENOMBRADO DE ESTACIONES SÍSMICAS (RSA)")
    logger.info(f"URL: {args.url} | Org: {args.org}")
    logger.info(f"Mapeos: {STATION_MAPPINGS}")
    if args.dry_run:
        logger.info("⚡ [MODO DRY-RUN ACTIVADO - No se realizarán cambios reales]")
    logger.info("=" * 65)

    client = influxdb_client.InfluxDBClient(
        url=args.url,
        token=args.token,
        org=args.org,
        timeout=60_000
    )

    if not client.ping():
        logger.error(f"No se pudo conectar a InfluxDB en {args.url}.")
        sys.exit(1)

    logger.info("✅ Conexión con InfluxDB establecida.")

    # Obtener límite de corte de retención para telemetry
    cutoff_time = get_retention_cutoff(client, logger, args.org, args.telemetry_bucket)

    # 1. Migrar telemetría estación por estación
    total_telemetry = 0
    for old_st, new_st in STATION_MAPPINGS.items():
        count = migrate_telemetry_station(
            client=client,
            logger=logger,
            org=args.org,
            bucket=args.telemetry_bucket,
            old_station=old_st,
            new_station=new_st,
            batch_size=args.batch_size,
            cutoff_time=cutoff_time,
            dry_run=args.dry_run
        )
        total_telemetry += count

    # 2. Migrar catálogo de eventos si aplica
    total_events = migrate_events_catalog(
        client=client,
        logger=logger,
        org=args.org,
        bucket=args.events_bucket,
        dry_run=args.dry_run
    )

    logger.info("=" * 65)
    logger.info("RESUMEN GENERAL DE MIGRACIÓN:")
    logger.info(f"  - Puntos de telemetría procesados: {total_telemetry}")
    logger.info(f"  - Eventos de catálogo actualizados: {total_events}")
    if args.dry_run:
        logger.info("⚡ Simulación finalizada. Para aplicar cambios ejecuta sin --dry-run.")
    else:
        logger.info("🎉 ¡Migración de estaciones completada con éxito!")
    logger.info("=" * 65)


if __name__ == "__main__":
    main()
