#!/usr/bin/env bash
# ==============================================================================
# Red Sísmica del Austro (RSA) - Stack TIG
# Script de Ejecución Aislada para el Simulador de Alertas MQTT
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="/tmp/rsa_simulator_venv"

echo "======================================================================"
echo "  RSA - Inicializando Entorno Virtual para Pruebas MQTT"
echo "======================================================================"

# 1. Crear entorno virtual si no existe
if [ ! -d "$VENV_DIR" ]; then
    echo "[i] Creando entorno virtual en $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
fi

# 2. Activar entorno virtual
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# 3. Instalar/Verificar dependencias
echo "[i] Verificando librería paho-mqtt..."
pip install -q -r "$SCRIPT_DIR/requirements.txt"

# 4. Función de limpieza y desactivación asegurada al salir
cleanup() {
    echo ""
    echo "[i] Desactivando entorno virtual..."
    deactivate 2>/dev/null || true
    echo "[✓] Entorno cerrado limpiamente. No hay procesos en segundo plano."
    echo "======================================================================"
}
trap cleanup EXIT

# 5. Ejecutar el simulador con todos los argumentos pasados
python3 "$SCRIPT_DIR/simulador_alertas_mqtt.py" "$@"
