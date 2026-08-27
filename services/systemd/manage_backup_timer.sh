#!/usr/bin/env bash
# ==============================================================================
# manage_backup_timer.sh — Gestor de Automatización Systemd (Backup InfluxDB)
# Red Sísmica del Austro (RSA)
#
# Permite instalar, desinstalar, inspeccionar y probar el timer y servicio systemd
# en cualquier servidor resolviendo dinámicamente rutas, usuarios y grupos sin
# valores hardcodeados en el repositorio.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Archivos de plantilla y destino
SERVICE_TEMPLATE="$SCRIPT_DIR/rsa-backup-events.service.template"
TIMER_TEMPLATE="$SCRIPT_DIR/rsa-backup-events.timer.template"
SYSTEMD_DIR="/etc/systemd/system"
TARGET_SERVICE="$SYSTEMD_DIR/rsa-backup-events.service"
TARGET_TIMER="$SYSTEMD_DIR/rsa-backup-events.timer"

# Opciones por defecto
ACTION=""
TARGET_USER=""
SCHEDULE_CALENDAR="*-*-* 02:00:00 UTC"
RANDOM_DELAY="300"
DRY_RUN=false
FOLLOW_LOGS=false

# Función de ayuda
show_help() {
    cat << 'EOF'
Uso: manage_backup_timer.sh [ACCION] [OPCIONES]

Acciones principales:
  --install              Renderiza plantillas e instala el servicio y timer en systemd
  --uninstall            Detiene, deshabilita y elimina el servicio y timer de systemd
  --status               Muestra el estado actual del timer, próxima ejecución y último servicio
  --run-now              Dispara inmediatamente una ejecución de prueba del servicio vía systemd
  --logs                 Muestra las últimas entradas de registro en journald del backup

Opciones de configuración:
  --user USUARIO         Usuario del sistema bajo el cual correrá el servicio (default: usuario actual / SUDO_USER)
  --time "EXPRESION"     Expresión OnCalendar de systemd (default: "*-*-* 02:00:00 UTC")
  --delay SEGUNDOS       Retardo aleatorio máximo en segundos (default: 300)
  --follow, -f           En combinación con --logs, sigue los logs en tiempo real
  --dry-run              Muestra los archivos que se generarían sin aplicar cambios en el sistema
  -h, --help             Muestra este mensaje de ayuda

Ejemplos:
  sudo ./manage_backup_timer.sh --install
  sudo ./manage_backup_timer.sh --install --time "*-*-* 03:30:00 UTC"
  ./manage_backup_timer.sh --status
  sudo ./manage_backup_timer.sh --run-now
  ./manage_backup_timer.sh --logs
  sudo ./manage_backup_timer.sh --uninstall
EOF
}

# Parseo de argumentos
while [[ $# -gt 0 ]]; do
    case "$1" in
        --install)
            ACTION="install"
            shift
            ;;
        --uninstall)
            ACTION="uninstall"
            shift
            ;;
        --status)
            ACTION="status"
            shift
            ;;
        --run-now)
            ACTION="run-now"
            shift
            ;;
        --logs)
            ACTION="logs"
            shift
            ;;
        --user)
            TARGET_USER="$2"
            shift 2
            ;;
        --time)
            SCHEDULE_CALENDAR="$2"
            shift 2
            ;;
        --delay)
            RANDOM_DELAY="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --follow|-f)
            FOLLOW_LOGS=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "[ERROR] Argumento desconocido: $1" >&2
            echo "Usa '$0 --help' para ver los comandos disponibles." >&2
            exit 1
            ;;
    esac
done

if [ -z "$ACTION" ]; then
    echo "[ERROR] Debes especificar una acción (--install, --uninstall, --status, --run-now, --logs)." >&2
    echo "Usa '$0 --help' para obtener ayuda." >&2
    exit 1
fi

# Función para verificar privilegios de superusuario
require_root() {
    if [ "$EUID" -ne 0 ] && [ "$DRY_RUN" = false ]; then
        echo "[ERROR] Esta acción requiere privilegios de superusuario (ejecuta con sudo)." >&2
        exit 1
    fi
}

# Detección dinámica de entorno
resolve_environment() {
    # 1. Determinar usuario del sistema
    if [ -n "$TARGET_USER" ]; then
        SYSTEM_USER="$TARGET_USER"
    elif [ -n "${SUDO_USER:-}" ]; then
        SYSTEM_USER="$SUDO_USER"
    else
        SYSTEM_USER="$USER"
    fi

    # 2. Validar que el usuario exista
    if ! id "$SYSTEM_USER" &>/dev/null; then
        echo "[ERROR] El usuario '$SYSTEM_USER' no existe en el sistema." >&2
        exit 1
    fi

    # 3. Determinar grupo primario del usuario
    SYSTEM_GROUP="$(id -gn "$SYSTEM_USER")"

    # 4. Rutas requeridas
    WORKING_DIR="$REPO_ROOT/scripts/db_sync"
    BACKUP_SCRIPT="$REPO_ROOT/scripts/db_sync/backup_events.sh"
    ENV_FILE="$REPO_ROOT/services/docker-unified/.env"
    BASH_BIN="$(which bash || echo '/bin/bash')"

    # 5. Validar existencia de archivos core
    if [ ! -f "$BACKUP_SCRIPT" ]; then
        echo "[ERROR] No se encontró el script de respaldo en: $BACKUP_SCRIPT" >&2
        exit 1
    fi
    if [ ! -f "$ENV_FILE" ]; then
        echo "[WARN] No se encontró el archivo de entorno en: $ENV_FILE"
        echo "       Asegúrate de copiar .env.example a .env antes de la ejecución del timer."
    fi

    # 6. Validar pertenencia a grupo docker
    if ! id -nG "$SYSTEM_USER" | grep -qw "docker"; then
        echo "[WARN] El usuario '$SYSTEM_USER' no pertenece al grupo 'docker'."
        echo "       El servicio systemd podría fallar al invocar docker. Se recomienda:"
        echo "       sudo usermod -aG docker $SYSTEM_USER"
    fi
}

# ------------------------------------------------------------------------------
# Acción: INSTALL
# ------------------------------------------------------------------------------
do_install() {
    require_root
    resolve_environment

    echo "=============================================================================="
    echo " RSA - Instalando Automatización Systemd (Backup Diario InfluxDB)"
    echo "=============================================================================="
    echo "[INFO] Parámetros resueltos dinámicamente:"
    echo "  - Raíz del repositorio  : $REPO_ROOT"
    echo "  - Usuario de ejecución  : $SYSTEM_USER"
    echo "  - Grupo de ejecución    : $SYSTEM_GROUP"
    echo "  - Directorio de trabajo : $WORKING_DIR"
    echo "  - Script de respaldo    : $BACKUP_SCRIPT"
    echo "  - Archivo .env          : $ENV_FILE"
    echo "  - Intérprete Bash       : $BASH_BIN"
    echo "  - Cronograma (UTC)      : $SCHEDULE_CALENDAR"
    echo "  - Retardo aleatorio     : ${RANDOM_DELAY}s"
    echo "------------------------------------------------------------------------------"

    # Validar plantillas
    if [ ! -f "$SERVICE_TEMPLATE" ] || [ ! -f "$TIMER_TEMPLATE" ]; then
        echo "[ERROR] Faltan archivos de plantilla en: $SCRIPT_DIR" >&2
        exit 1
    fi

    # Asegurar permisos de ejecución en el script de respaldo
    chmod +x "$BACKUP_SCRIPT" 2>/dev/null || true

    # Renderizar servicio
    RENDERED_SERVICE=$(sed \
        -e "s|@REPO_ROOT@|$REPO_ROOT|g" \
        -e "s|@SYSTEM_USER@|$SYSTEM_USER|g" \
        -e "s|@SYSTEM_GROUP@|$SYSTEM_GROUP|g" \
        -e "s|@WORKING_DIR@|$WORKING_DIR|g" \
        -e "s|@BACKUP_SCRIPT@|$BACKUP_SCRIPT|g" \
        -e "s|@ENV_FILE@|$ENV_FILE|g" \
        -e "s|@BASH_BIN@|$BASH_BIN|g" \
        "$SERVICE_TEMPLATE")

    # Renderizar timer
    RENDERED_TIMER=$(sed \
        -e "s|@REPO_ROOT@|$REPO_ROOT|g" \
        -e "s|@SCHEDULE_CALENDAR@|$SCHEDULE_CALENDAR|g" \
        -e "s|@SCHEDULE_TIME@|$SCHEDULE_CALENDAR|g" \
        -e "s|@RANDOM_DELAY@|$RANDOM_DELAY|g" \
        "$TIMER_TEMPLATE")

    if [ "$DRY_RUN" = true ]; then
        echo "[DRY-RUN] Contenido de $TARGET_SERVICE:"
        echo "$RENDERED_SERVICE"
        echo ""
        echo "[DRY-RUN] Contenido de $TARGET_TIMER:"
        echo "$RENDERED_TIMER"
        echo "[DRY-RUN] Modo simulación completado. No se realizaron cambios."
        return 0
    fi

    # Escribir unidades en systemd
    echo "[INFO] Escribiendo $TARGET_SERVICE..."
    echo "$RENDERED_SERVICE" > "$TARGET_SERVICE"
    chmod 644 "$TARGET_SERVICE"

    echo "[INFO] Escribiendo $TARGET_TIMER..."
    echo "$RENDERED_TIMER" > "$TARGET_TIMER"
    chmod 644 "$TARGET_TIMER"

    # Recargar y habilitar
    echo "[INFO] Recargando configuración de systemd (daemon-reload)..."
    systemctl daemon-reload

    echo "[INFO] Habilitando e iniciando rsa-backup-events.timer..."
    systemctl enable --now rsa-backup-events.timer

    echo ""
    echo "=============================================================================="
    echo " [SUCCESS] Automatización instalada y activa exitosamente."
    echo "=============================================================================="
    echo ""
    systemctl list-timers rsa-backup-events.timer --no-pager
}

# ------------------------------------------------------------------------------
# Acción: UNINSTALL
# ------------------------------------------------------------------------------
do_uninstall() {
    require_root

    echo "=============================================================================="
    echo " RSA - Desinstalando Automatización Systemd"
    echo "=============================================================================="

    if [ "$DRY_RUN" = true ]; then
        echo "[DRY-RUN] Se detendrían y eliminarían $TARGET_TIMER y $TARGET_SERVICE."
        return 0
    fi

    # Detener y deshabilitar timer
    if systemctl is-active --quiet rsa-backup-events.timer 2>/dev/null || systemctl is-enabled --quiet rsa-backup-events.timer 2>/dev/null; then
        echo "[INFO] Deteniendo y deshabilitando rsa-backup-events.timer..."
        systemctl disable --now rsa-backup-events.timer 2>/dev/null || true
    fi

    # Detener servicio si estuviera corriendo
    if systemctl is-active --quiet rsa-backup-events.service 2>/dev/null; then
        echo "[INFO] Deteniendo rsa-backup-events.service..."
        systemctl stop rsa-backup-events.service 2>/dev/null || true
    fi

    # Eliminar archivos
    echo "[INFO] Eliminando archivos de unidad en $SYSTEMD_DIR..."
    rm -f "$TARGET_SERVICE" "$TARGET_TIMER"

    # Recargar y resetear fallos
    echo "[INFO] Recargando systemd..."
    systemctl daemon-reload
    systemctl reset-failed 2>/dev/null || true

    echo "=============================================================================="
    echo " [SUCCESS] Automatización desinstalada y limpiada por completo."
    echo "=============================================================================="
}

# ------------------------------------------------------------------------------
# Acción: STATUS
# ------------------------------------------------------------------------------
do_status() {
    echo "=============================================================================="
    echo " RSA - Estado del Timer y Próxima Ejecución"
    echo "=============================================================================="
    if [ ! -f "$TARGET_TIMER" ]; then
        echo "[WARN] La unidad $TARGET_TIMER no está instalada."
        echo "       Ejecuta 'sudo $0 --install' para desplegarla."
        exit 0
    fi

    echo "--- 🕒 Próxima Ejecución Programada ---"
    systemctl list-timers rsa-backup-events.timer --no-pager || true
    echo ""

    echo "--- ⚙️ Estado de la Unidad Timer ---"
    systemctl status rsa-backup-events.timer --no-pager || true
    echo ""

    echo "--- 📜 Último Estado del Servicio ---"
    systemctl status rsa-backup-events.service --no-pager || true
}

# ------------------------------------------------------------------------------
# Acción: RUN-NOW
# ------------------------------------------------------------------------------
do_run_now() {
    require_root
    if [ ! -f "$TARGET_SERVICE" ]; then
        echo "[ERROR] El servicio $TARGET_SERVICE no está instalado." >&2
        echo "        Ejecuta primero: sudo $0 --install" >&2
        exit 1
    fi

    echo "=============================================================================="
    echo " RSA - Ejecutando Respaldo Manual vía Systemd (rsa-backup-events.service)"
    echo "=============================================================================="
    echo "[INFO] Disparando ejecución sincrónica del servicio..."
    
    if systemctl start rsa-backup-events.service; then
        echo ""
        echo "=============================================================================="
        echo " [SUCCESS] Servicio ejecutado correctamente."
        echo "=============================================================================="
        echo ""
        journalctl -u rsa-backup-events.service -n 25 --no-pager
    else
        echo "[ERROR] Falló la ejecución del servicio." >&2
        echo "--- Logs de error recientes ---"
        journalctl -u rsa-backup-events.service -n 30 --no-pager
        exit 1
    fi
}

# ------------------------------------------------------------------------------
# Acción: LOGS
# ------------------------------------------------------------------------------
do_logs() {
    echo "=============================================================================="
    echo " RSA - Registros de Respaldo en Journald (rsa-backup-events.service)"
    echo "=============================================================================="
    if [ "$FOLLOW_LOGS" = true ]; then
        journalctl -u rsa-backup-events.service -f
    else
        journalctl -u rsa-backup-events.service -n 50 --no-pager
    fi
}

# Ejecución principal según acción
case "$ACTION" in
    install)
        do_install
        ;;
    uninstall)
        do_uninstall
        ;;
    status)
        do_status
        ;;
    run-now)
        do_run_now
        ;;
    logs)
        do_logs
        ;;
esac
