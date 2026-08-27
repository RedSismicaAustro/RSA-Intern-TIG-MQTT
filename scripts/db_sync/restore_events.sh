#!/usr/bin/env bash
# ==============================================================================
# restore_events.sh — Protocolo de Restauración Destructiva InfluxDB (rsa_events)
# Red Sísmica del Austro (RSA)
#
# Descarga un snapshot binario (.tar.gz) desde Google Drive, elimina el bucket
# 'rsa_events' actual y restaura el estado exacto del snapshot.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_ENV_FILE="$SCRIPT_DIR/../../services/docker-unified/.env"

DATE_TARGET=""
USE_LATEST=false
AUTO_CONFIRM=false
ENV_FILE="$DEFAULT_ENV_FILE"
CONTAINER="rsa-influxdb"
TMP_DIR="/tmp/rsa_restore_$$"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --date)
            DATE_TARGET="$2"
            shift 2
            ;;
        --latest)
            USE_LATEST=true
            shift
            ;;
        --yes|-y)
            AUTO_CONFIRM=true
            shift
            ;;
        --env-file)
            ENV_FILE="$2"
            shift 2
            ;;
        -h|--help)
            echo "Uso: $0 [--latest | --date YYYY-MM-DD] [--yes] [--env-file PATH]"
            echo "  --latest            Restaura el respaldo más reciente disponible en Google Drive"
            echo "  --date YYYY-MM-DD   Restaura el respaldo de una fecha específica"
            echo "  --yes, -y           Omite confirmación interactiva de borrado destructivo"
            echo "  --env-file PATH     Ruta personalizada al archivo .env"
            exit 0
            ;;
        *)
            echo "[ERROR] Argumento desconocido: $1" >&2
            exit 1
            ;;
    esac
done

if [ "$USE_LATEST" = false ] && [ -z "$DATE_TARGET" ]; then
    echo "[ERROR] Debes especificar --latest o --date YYYY-MM-DD." >&2
    exit 1
fi

cleanup() {
    rm -rf "$TMP_DIR"
    docker exec "$CONTAINER" rm -rf /tmp/restore_data 2>/dev/null || true
}
trap cleanup EXIT

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
fi

INFLUXDB_ORG="${INFLUXDB_ORG:-rsa}"
INFLUXDB_EVENTS_BUCKET="${INFLUXDB_EVENTS_BUCKET:-rsa_events}"
RCLONE_DEST="${RCLONE_REMOTE:-gdrive:RSA-Backups/influxdb}"

# Verificar contenedor
if ! docker inspect "$CONTAINER" --format='{{.State.Running}}' 2>/dev/null | grep -q true; then
    echo "[ERROR] Contenedor $CONTAINER no está en ejecución." >&2
    exit 1
fi

# Token InfluxDB
if [ -z "${INFLUXDB_TOKEN:-}" ]; then
    INFLUXDB_TOKEN=$(docker exec "$CONTAINER" sh -c 'echo "$DOCKER_INFLUXDB_INIT_ADMIN_TOKEN"' 2>/dev/null || true)
fi

# 2. Determinar archivo de respaldo a restaurar
if [ "$USE_LATEST" = true ]; then
    echo "[INFO] Buscando respaldo más reciente en Google Drive (${RCLONE_DEST}/)..."
    LATEST_FILE=$(rclone lsf "$RCLONE_DEST/" --files-only 2>/dev/null | grep -E '^rsa_events_[0-9]{4}-[0-9]{2}-[0-9]{2}\.tar\.gz$' | sort -r | head -n 1 || true)
    if [ -z "$LATEST_FILE" ]; then
        echo "[ERROR] No se encontraron archivos de respaldo en $RCLONE_DEST/" >&2
        exit 1
    fi
    BACKUP_FILE="$LATEST_FILE"
else
    BACKUP_FILE="rsa_events_${DATE_TARGET}.tar.gz"
fi

echo "[INFO] Archivo de respaldo seleccionado: $BACKUP_FILE"

# 3. Descargar archivo desde Google Drive
mkdir -p "$TMP_DIR/snapshot"
echo "[INFO] Descargando $BACKUP_FILE desde Google Drive..."
if ! rclone copy "$RCLONE_DEST/$BACKUP_FILE" "$TMP_DIR/"; then
    echo "[ERROR] Falló la descarga de $BACKUP_FILE desde $RCLONE_DEST" >&2
    exit 1
fi

# 4. Extraer snapshot
echo "[INFO] Descomprimiendo snapshot..."
tar xzf "$TMP_DIR/$BACKUP_FILE" -C "$TMP_DIR/snapshot"

# 5. Obtener conteo actual de eventos antes de destruir el bucket
COUNT_QUERY="from(bucket: \"${INFLUXDB_EVENTS_BUCKET}\")
  |> range(start: 0)
  |> filter(fn: (r) => r._measurement == \"seismic_event\" and r._field == \"stations\")
  |> count()"

CURRENT_COUNT_RAW=$(docker exec "$CONTAINER" influx query "$COUNT_QUERY" \
    --org "$INFLUXDB_ORG" \
    --token "$INFLUXDB_TOKEN" \
    --raw 2>/dev/null || true)

CURRENT_EVENTS="desconocido"
if [ -n "$CURRENT_COUNT_RAW" ]; then
    # Extraer el valor numérico de la última línea de resultados
    VAL=$(echo "$CURRENT_COUNT_RAW" | tail -n 1 | awk -F',' '{print $6}' | tr -d ' ' || true)
    if [[ "$VAL" =~ ^[0-9]+$ ]]; then
        CURRENT_EVENTS="$VAL"
    fi
fi

# 6. Confirmación destructiva
echo ""
echo "=============================================================================="
echo " ⚠️ ADVERTENCIA CRÍTICA: OPERACIÓN DESTRUCTIVA"
echo "=============================================================================="
echo " Se ELIMINARÁ por completo el bucket '$INFLUXDB_EVENTS_BUCKET' en InfluxDB."
echo " Eventos registrados actualmente en la base: $CURRENT_EVENTS"
echo " Se restaurará la copia desde: $BACKUP_FILE"
echo "=============================================================================="
echo ""

if [ "$AUTO_CONFIRM" = false ]; then
    read -r -p "¿Estás seguro de que deseas destruir y restaurar el catálogo? (escribe 'SI' para confirmar): " CONFIRMATION
    if [ "$CONFIRMATION" != "SI" ]; then
        echo "[CANCELADO] Restauración cancelada por el usuario."
        exit 0
    fi
fi

# 7. Copiar datos al contenedor
echo "[INFO] Copiando datos de snapshot al contenedor..."
docker exec "$CONTAINER" rm -rf /tmp/restore_data
docker cp "$TMP_DIR/snapshot/." "$CONTAINER:/tmp/restore_data/"

# 8. Borrar bucket actual
echo "[INFO] Eliminando bucket '$INFLUXDB_EVENTS_BUCKET'..."
docker exec "$CONTAINER" influx bucket delete \
    --name "$INFLUXDB_EVENTS_BUCKET" \
    --org "$INFLUXDB_ORG" \
    --token "$INFLUXDB_TOKEN" || echo "[WARN] El bucket no existía o ya fue eliminado."

# 9. Restaurar snapshot
echo "[INFO] Restaurando datos con 'influx restore'..."
if ! docker exec "$CONTAINER" influx restore /tmp/restore_data \
    --bucket "$INFLUXDB_EVENTS_BUCKET" \
    --org "$INFLUXDB_ORG" \
    --token "$INFLUXDB_TOKEN"; then
    echo "[ERROR] Falló el comando 'influx restore' dentro del contenedor." >&2
    exit 1
fi

# 10. Verificar integridad
echo "[INFO] Verificando integridad del catálogo restaurado..."
RESTORED_COUNT_RAW=$(docker exec "$CONTAINER" influx query "$COUNT_QUERY" \
    --org "$INFLUXDB_ORG" \
    --token "$INFLUXDB_TOKEN" \
    --raw 2>/dev/null || true)

RESTORED_EVENTS="desconocido"
if [ -n "$RESTORED_COUNT_RAW" ]; then
    VAL=$(echo "$RESTORED_COUNT_RAW" | tail -n 1 | awk -F',' '{print $6}' | tr -d ' ' || true)
    if [[ "$VAL" =~ ^[0-9]+$ ]]; then
        RESTORED_EVENTS="$VAL"
    fi
fi

echo ""
echo "=============================================================================="
echo " [SUCCESS] Restauración completada exitosamente."
echo " Origen              : $BACKUP_FILE"
echo " Eventos previos     : $CURRENT_EVENTS"
echo " Eventos restaurados : $RESTORED_EVENTS"
echo "=============================================================================="
