#!/bin/bash
# ==============================================================================
# Script de Inicio Rápido - Docker Compose Unificado
# ==============================================================================
#
# Este script automatiza el proceso de configuración e inicio del stack TIG

set -e  # Salir si hay errores

echo "=================================="
echo "TIG Stack - Inicio Rápido"
echo "Red Sísmica del Austro (RSA)"
echo "=================================="
echo ""

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Verificar que Docker está instalado
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker no está instalado${NC}"
    echo "Instala Docker desde: https://docs.docker.com/get-docker/"
    exit 1
fi

# Verificar que Docker Compose está disponible
if ! docker compose version &> /dev/null && ! docker-compose --version &> /dev/null; then
    echo -e "${RED}Error: Docker Compose no está disponible${NC}"
    exit 1
fi

# Usar docker compose (v2) o docker-compose (v1)
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

echo -e "${GREEN}✓${NC} Docker y Docker Compose detectados"
echo ""

# Verificar si existe archivo .env
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠ Archivo .env no encontrado${NC}"
    echo "Creando .env desde .env.example..."

    if [ -f .env.example ]; then
        cp .env.example .env
        echo -e "${GREEN}✓${NC} Archivo .env creado"
        echo ""
        echo -e "${YELLOW}IMPORTANTE:${NC} Edita el archivo .env con tus credenciales reales:"
        echo "  nano .env"
        echo ""
        read -p "¿Has configurado el archivo .env? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo -e "${RED}Configuración cancelada${NC}"
            echo "Edita .env y ejecuta este script nuevamente"
            exit 1
        fi
    else
        echo -e "${RED}Error: .env.example no encontrado${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✓${NC} Archivo .env encontrado"
fi

# Verificar configuración de Telegraf
TELEGRAF_CONF="../../scripts/telegraf/telegraf.conf"
if [ ! -f "$TELEGRAF_CONF" ]; then
    echo -e "${YELLOW}⚠ Advertencia: Configuración de Telegraf no encontrada en:${NC}"
    echo "  $TELEGRAF_CONF"
    echo ""
    read -p "¿Continuar de todos modos? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo ""
echo "=================================="
echo "Iniciando Stack TIG..."
echo "=================================="
echo ""

# Detener contenedores existentes (si los hay)
echo "Deteniendo contenedores previos (si existen)..."
$DOCKER_COMPOSE down 2>/dev/null || true

# Iniciar servicios
echo ""
echo "Iniciando servicios con Docker Compose..."
$DOCKER_COMPOSE up -d

# Esperar a que los servicios estén saludables
echo ""
echo "Esperando a que los servicios estén listos..."
echo "(Esto puede tomar 30-60 segundos)"
echo ""

sleep 5

# Verificar estado de los servicios
MAX_WAIT=60
ELAPSED=0
ALL_HEALTHY=false

while [ $ELAPSED -lt $MAX_WAIT ]; do
    INFLUXDB_STATUS=$($DOCKER_COMPOSE ps influxdb --format json 2>/dev/null | grep -o '"Health":"[^"]*"' | cut -d'"' -f4 || echo "starting")
    GRAFANA_STATUS=$($DOCKER_COMPOSE ps grafana --format json 2>/dev/null | grep -o '"Health":"[^"]*"' | cut -d'"' -f4 || echo "starting")
    TELEGRAF_STATUS=$($DOCKER_COMPOSE ps telegraf --format json 2>/dev/null | grep -o '"State":"[^"]*"' | cut -d'"' -f4 || echo "starting")

    if [ "$INFLUXDB_STATUS" = "healthy" ] && [ "$GRAFANA_STATUS" = "healthy" ] && [ "$TELEGRAF_STATUS" = "running" ]; then
        ALL_HEALTHY=true
        break
    fi

    printf "."
    sleep 2
    ELAPSED=$((ELAPSED + 2))
done

echo ""
echo ""

if [ "$ALL_HEALTHY" = true ]; then
    echo -e "${GREEN}✓ Todos los servicios están operativos${NC}"
else
    echo -e "${YELLOW}⚠ Algunos servicios están iniciando. Verifica con:${NC}"
    echo "  $DOCKER_COMPOSE ps"
    echo "  $DOCKER_COMPOSE logs -f"
fi

# Mostrar estado
echo ""
echo "=================================="
echo "Estado de los Servicios"
echo "=================================="
$DOCKER_COMPOSE ps

echo ""
echo "=================================="
echo "Acceso a las Interfaces Web"
echo "=================================="
echo ""
echo -e "${GREEN}InfluxDB UI:${NC} http://localhost:8086"
echo "  Usuario: \$(grep INFLUXDB_ADMIN_USER .env | cut -d'=' -f2)"
echo ""
echo -e "${GREEN}Grafana:${NC}     http://localhost:3000"
echo "  Usuario: \$(grep GRAFANA_ADMIN_USER .env | cut -d'=' -f2)"
echo ""
echo "=================================="
echo "Comandos Útiles"
echo "=================================="
echo ""
echo "Ver logs en tiempo real:"
echo "  $DOCKER_COMPOSE logs -f"
echo ""
echo "Ver logs de un servicio específico:"
echo "  $DOCKER_COMPOSE logs -f telegraf"
echo ""
echo "Reiniciar un servicio:"
echo "  $DOCKER_COMPOSE restart telegraf"
echo ""
echo "Detener todos los servicios:"
echo "  $DOCKER_COMPOSE down"
echo ""
echo "=================================="
echo ""
echo -e "${GREEN}✓ Stack TIG iniciado exitosamente${NC}"
echo ""
