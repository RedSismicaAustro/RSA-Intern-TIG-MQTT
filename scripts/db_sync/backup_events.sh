#!/usr/bin/env bash
# ==============================================================================
# backup_events.sh — Protocolo de Respaldo Diario InfluxDB (rsa_events)
# Red Sísmica del Austro (RSA)
#
# Genera:
#   1. Snapshot binario nativo (influx backup) comprimido en .tar.gz
#   2. Exportación tabular legible en formato .csv con Flux pivot()
# Sube a Google Drive con rclone y purga respaldos anteriores a N días.
# Notifica el resultado a MQTT (rsa/seismic/smart/system/backup) con QoS 1.
# ==============================================================================

set -euo pipefail

# Directorios de referencia
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_ENV_FILE="$SCRIPT_DIR/../../services/docker-unified/.env"
COMPOSE_DIR="$SCRIPT_DIR/../../services/docker-unified"

# Opciones por defecto
DRY_RUN=false
RETENTION_DAYS=7
ENV_FILE="$DEFAULT_ENV_FILE"
START_TIME=$(date +%s)
DATE_UTC=$(date -u +%Y-%m-%d)
BACKUP_NAME="rsa_events_${DATE_UTC}"
CONTAINER="rsa-influxdb"
TMP_DIR="/tmp/rsa_backup_${DATE_UTC}_$$"

# Parseo de argumentos
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --retention-days)
            RETENTION_DAYS="$2"
            shift 2
            ;;
        --env-file)
            ENV_FILE="$2"
            shift 2
            ;;
        -h|--help)
            echo "Uso: $0 [--dry-run] [--retention-days N] [--env-file PATH]"
            echo "  --dry-run           Ejecuta snapshot y CSV sin subir a Drive ni purgar"
            echo "  --retention-days N  Días de retención para purga en Drive (default: 7)"
            echo "  --env-file PATH     Ruta personalizada al archivo .env"
            exit 0
            ;;
        *)
            echo "[ERROR] Argumento desconocido: $1" >&2
            exit 1
            ;;
    esac
done

# Función de limpieza ante salida
cleanup() {
    rm -rf "$TMP_DIR"
    docker exec "$CONTAINER" rm -rf /tmp/backup 2>/dev/null || true
}
trap cleanup EXIT

# Función para notificar fallo
notify_failure() {
    local error_msg="$1"
    echo "[ERROR] $error_msg" >&2
    local duration=$(( $(date +%s) - START_TIME ))
    if docker compose -f "$COMPOSE_DIR/docker-compose.yml" ps --services 2>/dev/null | grep -q "db-sync"; then
        docker compose -f "$COMPOSE_DIR/docker-compose.yml" run --rm db-sync \
            mqtt_notify.py \
            --status failure \
            --error-message "$error_msg" \
            --drive-path "${RCLONE_DEST:-gdrive:DIA/Datos Estaciones/RSA-Backups/influxdb}" \
            --duration "$duration" 2>/dev/null || true
    fi
}

echo "=============================================================================="
echo " RSA - Inicio de Respaldo de Catálogo InfluxDB: ${BACKUP_NAME}"
echo "=============================================================================="

# 1. Cargar y sanitizar .env
if [ -f "$ENV_FILE" ]; then
    echo "[INFO] Cargando variables desde: $ENV_FILE"
    while IFS='=' read -r key value || [ -n "$key" ]; do
        [[ "$key" =~ ^[[:space:]]*# ]] && continue
        [[ -z "$key" ]] && continue
        key=$(echo "$key" | xargs)
        value=$(echo "$value" | tr -d '\r' | sed -e 's/^[[:space:]]*["'\''"]//' -e 's/["'\''"][[:space:]]*$//')
        if [ -n "$key" ]; then
            export "$key"="$value"
        fi
    done < "$ENV_FILE"
else
    echo "[WARN] No se encontró $ENV_FILE, usando variables del entorno actual."
fi

# Variables requeridas con defaults
INFLUXDB_ORG="${INFLUXDB_ORG:-rsa}"
INFLUXDB_EVENTS_BUCKET="${INFLUXDB_EVENTS_BUCKET:-rsa_events}"
RCLONE_DEST="${RCLONE_REMOTE:-gdrive:DIA/Datos Estaciones/RSA-Backups/influxdb}"
TELEGRAF_CLIENT_ID="${TELEGRAF_CLIENT_ID:-events-server}"

# 2. Verificar estado del contenedor InfluxDB
echo "[INFO] Verificando estado del contenedor $CONTAINER..."
if ! docker inspect "$CONTAINER" --format='{{.State.Running}}' 2>/dev/null | grep -q true; then
    notify_failure "Contenedor $CONTAINER no está en ejecución"
    exit 1
fi

# Obtener o verificar token de InfluxDB
if [ -z "${INFLUXDB_TOKEN:-}" ]; then
    INFLUXDB_TOKEN=$(docker exec "$CONTAINER" sh -c 'echo "$DOCKER_INFLUXDB_INIT_ADMIN_TOKEN"' 2>/dev/null || true)
fi

if [ -z "${INFLUXDB_TOKEN:-}" ]; then
    notify_failure "No se pudo obtener INFLUXDB_TOKEN para autenticación"
    exit 1
fi

# 3. Crear directorio temporal local
mkdir -p "$TMP_DIR/snapshot"

# 4. Generar snapshot binario nativo (influx backup)
echo "[INFO] Generando snapshot binario en contenedor $CONTAINER (bucket: $INFLUXDB_EVENTS_BUCKET)..."
docker exec "$CONTAINER" rm -rf /tmp/backup
if ! docker exec "$CONTAINER" influx backup /tmp/backup \
    --bucket "$INFLUXDB_EVENTS_BUCKET" \
    --org "$INFLUXDB_ORG" \
    --token "$INFLUXDB_TOKEN" >/dev/null; then
    notify_failure "Fallo al ejecutar 'influx backup' dentro del contenedor"
    exit 1
fi

echo "[INFO] Copiando y empaquetando snapshot binario..."
docker cp "$CONTAINER:/tmp/backup/." "$TMP_DIR/snapshot/"
tar czf "$TMP_DIR/${BACKUP_NAME}.tar.gz" -C "$TMP_DIR/snapshot" .
SNAPSHOT_SIZE=$(stat -c%s "$TMP_DIR/${BACKUP_NAME}.tar.gz")
echo "[OK] Snapshot binario creado: ${BACKUP_NAME}.tar.gz (${SNAPSHOT_SIZE} bytes)"

# 5. Exportar CSV legible con consulta Flux pivot()
echo "[INFO] Exportando catálogo a CSV legible..."
FLUX_QUERY="from(bucket: \"${INFLUXDB_EVENTS_BUCKET}\")
  |> range(start: 0)
  |> filter(fn: (r) => r._measurement == \"seismic_event\")
  |> pivot(rowKey: [\"_time\",\"event_id\"], columnKey: [\"_field\"], valueColumn: \"_value\")"

if ! docker exec "$CONTAINER" influx query "$FLUX_QUERY" \
    --org "$INFLUXDB_ORG" \
    --token "$INFLUXDB_TOKEN" \
    --raw > "$TMP_DIR/${BACKUP_NAME}.csv"; then
    notify_failure "Fallo al ejecutar consulta Flux para exportación CSV"
    exit 1
fi

CSV_SIZE=$(stat -c%s "$TMP_DIR/${BACKUP_NAME}.csv")
EVENTS_RAW=$(wc -l < "$TMP_DIR/${BACKUP_NAME}.csv" || echo 0)
EVENTS_COUNT=$(( EVENTS_RAW > 1 ? EVENTS_RAW - 1 : 0 ))
echo "[OK] Exportación CSV creada: ${BACKUP_NAME}.csv (${CSV_SIZE} bytes, ${EVENTS_COUNT} eventos)"

PURGED_COUNT=0

if [ "$DRY_RUN" = true ]; then
    echo "[INFO] Modo --dry-run activado: Se omite subida a Drive y rotación."
else
    # 6. Subir archivos a Google Drive vía rclone
    echo "[INFO] Subiendo archivos a Google Drive (${RCLONE_DEST}/)..."
    if ! rclone copy "$TMP_DIR/${BACKUP_NAME}.tar.gz" "$RCLONE_DEST/"; then
        notify_failure "Fallo al subir snapshot binario a $RCLONE_DEST"
        exit 1
    fi
    if ! rclone copy "$TMP_DIR/${BACKUP_NAME}.csv" "$RCLONE_DEST/"; then
        notify_failure "Fallo al subir archivo CSV a $RCLONE_DEST"
        exit 1
    fi

    # Verificar existencia en Drive
    if ! rclone ls "$RCLONE_DEST/${BACKUP_NAME}.tar.gz" >/dev/null; then
        notify_failure "Verificación de archivo en Drive fallida para ${BACKUP_NAME}.tar.gz"
        exit 1
    fi
    echo "[OK] Archivos verificados exitosamente en Google Drive."

    # 7. Purgar respaldos antiguos (> RETENTION_DAYS días)
    echo "[INFO] Verificando rotación de respaldos (> ${RETENTION_DAYS} días)..."
    NOW_SEC=$(date -u +%s)
    while IFS= read -r fname; do
        [ -z "$fname" ] && continue
        # Extraer fecha en formato YYYY-MM-DD
        fdate=$(echo "$fname" | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' || true)
        if [ -n "$fdate" ]; then
            file_sec=$(date -u -d "$fdate" +%s 2>/dev/null || echo 0)
            if [ "$file_sec" -gt 0 ]; then
                age_days=$(( (NOW_SEC - file_sec) / 86400 ))
                if [ "$age_days" -gt "$RETENTION_DAYS" ]; then
                    echo "[INFO] Purgando respaldo antiguo ($age_days días): $fname"
                    rclone deletefile "$RCLONE_DEST/$fname" || true
                    PURGED_COUNT=$(( PURGED_COUNT + 1 ))
                fi
            fi
        fi
    done < <(rclone lsf "$RCLONE_DEST/" --files-only 2>/dev/null || true)
    echo "[OK] Rotación completada. Respaldos purgados: ${PURGED_COUNT}"
fi

# 8. Notificar resultado exitoso vía MQTT
END_TIME=$(date +%s)
DURATION=$(( END_TIME - START_TIME ))

echo "[INFO] Publicando telemetría de respaldo a MQTT..."
docker compose -f "$COMPOSE_DIR/docker-compose.yml" run --rm db-sync \
    mqtt_notify.py \
    --status success \
    --events-count "$EVENTS_COUNT" \
    --snapshot-size "$SNAPSHOT_SIZE" \
    --csv-size "$CSV_SIZE" \
    --backup-file "${BACKUP_NAME}.tar.gz" \
    --drive-path "$RCLONE_DEST" \
    --duration "$DURATION" \
    --purged-count "$PURGED_COUNT" || echo "[WARN] No se pudo enviar notificación MQTT"

echo "=============================================================================="
echo " [SUCCESS] Respaldo completado en ${DURATION}s."
echo " Archivo Snapshot : ${BACKUP_NAME}.tar.gz (${SNAPSHOT_SIZE} bytes)"
echo " Archivo CSV      : ${BACKUP_NAME}.csv (${CSV_SIZE} bytes)"
echo " Eventos Totales  : ${EVENTS_COUNT}"
echo "=============================================================================="
