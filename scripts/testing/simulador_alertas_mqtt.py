#!/usr/bin/env python3
# ==============================================================================
# Red Sísmica del Austro (RSA) - Stack TIG
# Fase 4: Simulador Interactivo de Escenarios de Alertas y Telemetría MQTT
# ==============================================================================
"""
Script para la inyección de datos sintéticos MQTT hacia el broker de la RSA.
Permite evaluar y validar el comportamiento de los dashboards de Grafana:
- SeismicMonitor (Matriz de Diagnóstico Jerárquico)
- Health (Dashboard Detallado con Filas Colapsables)

Garantía de aislamiento:
  Cada escenario publica SIEMPRE en todos los tópicos base (state, health,
  acquisition, sensor, drive) con datos nominales saludables actualizados al
  segundo actual, e inyecta únicamente el error específico del escenario
  evaluado. De este modo se evita cualquier traslape de alertas previas.

Uso:
  python simulador_alertas_mqtt.py                     # Modo interactivo paso a paso
  python simulador_alertas_mqtt.py -e 1                # Ejecuta solo escenario 1
  python simulador_alertas_mqtt.py --list              # Lista los escenarios
"""

import sys
import os
import json
import time
import argparse
from datetime import datetime, timezone

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("\n[ERROR] La librería 'paho-mqtt' no está instalada.")
    print("Por favor instala las dependencias en tu entorno virtual:")
    print("  pip install -r requirements.txt\n")
    sys.exit(1)

# Configuración por defecto del Broker MQTT
DEFAULT_BROKER = os.getenv("MQTT_BROKER", "174.138.41.251")
DEFAULT_PORT = int(os.getenv("MQTT_PORT", "1883"))
DEFAULT_USER = os.getenv("MQTT_USERNAME", "rsa")
DEFAULT_PASS = os.getenv("MQTT_PASSWORD", "RSAiotace2023")
DEFAULT_STATION = "TEST"


def get_current_iso_time():
    """Retorna la fecha/hora UTC actual del sistema en formato ISO 8601."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def publish_mqtt_messages(broker, port, user, password, messages):
    """
    Publica una lista de tuplas (topic, payload_dict) en el broker MQTT y desconecta.
    """
    client_id = f"rsa-simulator-{int(time.time())}"
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    except AttributeError:
        client = mqtt.Client(client_id=client_id)

    if user and password:
        client.username_pw_set(user, password)

    try:
        client.connect(broker, port, keepalive=30)
    except Exception as e:
        print(f"[ERROR] No se pudo conectar al broker MQTT ({broker}:{port}): {e}")
        return False

    client.loop_start()
    try:
        for topic, payload in messages:
            payload_str = json.dumps(payload)
            res = client.publish(topic, payload_str, qos=1, retain=True)
            res.wait_for_publish(timeout=5)
            print(f"  -> Publicado en: {topic}")
            print(f"     Payload: {payload_str}")
        time.sleep(0.5)  # Breve margen para completar transmisión en broker
    finally:
        client.loop_stop()
        client.disconnect()

    return True


# ==============================================================================
# Generación de Payloads Base Nominales
# ==============================================================================

def get_nominal_payloads(station_id, now):
    """
    Genera el conjunto completo de payloads en estado 100% nominal y saludable.
    """
    return {
        "state": (
            f"rsa/seismic/smart/{station_id}/telemetry/state",
            {
                "status": "online",
                "timestamp": now
            }
        ),
        "health": (
            f"rsa/seismic/smart/{station_id}/telemetry/health",
            {
                "disk_percent": 45.0,
                "cpu_temp_c": 48.0,
                "ram_percent": 28.0,
                "load_avg_15m": 0.35,
                "throttled": "0x0",
                "timestamp": now
            }
        ),
        "acquisition": (
            f"rsa/seismic/smart/{station_id}/status/acquisition",
            {
                "status": "ok",
                "reason": "nominal",
                "last_frame_utc": now,
                "age_seconds": 1.2,
                "threshold_seconds": 300,
                "station_id": station_id,
                "timestamp": now
            }
        ),
        "sensor": (
            f"rsa/seismic/smart/{station_id}/status/sensor",
            {
                "status": "ok",
                "ax": 0.002,
                "ay": -0.001,
                "az": 9.805,
                "clock_source": "GPS",
                "clock_error": None,
                "reason": "nominal",
                "station_id": station_id,
                "timestamp": now
            }
        ),
        "drive": (
            f"rsa/seismic/smart/{station_id}/status/drive",
            {
                "status": "ok",
                "pending_mseed": 0,
                "failed_uploads_protected": 0,
                "free_disk_percent": 55.0,
                "reason": "all_synced",
                "last_upload_utc": now,
                "station_id": station_id,
                "timestamp": now
            }
        )
    }


def build_scenario_messages(station_id, now, overrides=None):
    """
    Retorna la lista de los 5 mensajes MQTT actualizados al segundo exacto,
    con los 4 canales en nominal y únicamente el canal anómalo sobreescrito.
    """
    payloads = get_nominal_payloads(station_id, now)
    if overrides:
        for canal, tupla_msg in overrides.items():
            payloads[canal] = tupla_msg
    return [
        payloads["state"],
        payloads["health"],
        payloads["acquisition"],
        payloads["sensor"],
        payloads["drive"]
    ]


# ==============================================================================
# Definición de Escenarios de Prueba
# ==============================================================================

def get_scenarios_meta():
    """
    Retorna los metadatos y constructores de mensajes para cada escenario.
    """
    return [
        {
            "id": 1,
            "nombre": "Estado Nominal Completo (Todo OK)",
            "descripcion": "Todos los subsistemas saludables. Conectividad online, sin alertas.",
            "diag_esperado": "OK",
            "color_esperado": "Verde",
            "build_fn": lambda s, now: build_scenario_messages(s, now)
        },
        {
            "id": 2,
            "nombre": "Falla de Google Drive (Advertencia de Sincronización)",
            "descripcion": "Adquisición y Sensor OK. Drive en warning con 5 miniSEED pendientes y 2 protegidos.",
            "diag_esperado": "Drive",
            "color_esperado": "Amarillo (semi-dark-yellow)",
            "build_fn": lambda s, now: build_scenario_messages(s, now, overrides={
                "drive": (
                    f"rsa/seismic/smart/{s}/status/drive",
                    {
                        "status": "warning",
                        "pending_mseed": 5,
                        "failed_uploads_protected": 2,
                        "free_disk_percent": 48.0,
                        "reason": "upload_retry_retained",
                        "last_upload_utc": now,
                        "station_id": s,
                        "timestamp": now
                    }
                )
            })
        },
        {
            "id": 3,
            "nombre": "Incoherencia del Sensor Triaxial (Error Físico en Eje Z)",
            "descripcion": "Adquisición y Drive OK. Sensor con aceleración Z anómala (0.10 m/s², fuera de rango 9.81 ± 0.8).",
            "diag_esperado": "Sensor",
            "color_esperado": "Rojo (dark-red)",
            "build_fn": lambda s, now: build_scenario_messages(s, now, overrides={
                "sensor": (
                    f"rsa/seismic/smart/{s}/status/sensor",
                    {
                        "status": "error",
                        "ax": -0.85,
                        "ay": 2.14,
                        "az": 0.10,
                        "clock_source": "GPS",
                        "clock_error": "accelerometer_anomaly",
                        "reason": "accelerometer_anomaly",
                        "station_id": s,
                        "timestamp": now
                    }
                )
            })
        },
        {
            "id": 4,
            "nombre": "Pipeline de Adquisición Detenido (Watchdog Ring Buffer)",
            "descripcion": "Sensor y Drive OK. Watchdog reporta 450 s sin frames recibidos (age > 300 s).",
            "diag_esperado": "Adquisicion",
            "color_esperado": "Rojo (dark-red, máxima jerarquía sobre Sensor y Drive)",
            "build_fn": lambda s, now: build_scenario_messages(s, now, overrides={
                "acquisition": (
                    f"rsa/seismic/smart/{s}/status/acquisition",
                    {
                        "status": "error",
                        "age_seconds": 450.0,
                        "threshold_seconds": 300,
                        "last_frame_utc": now,
                        "reason": "stale_data",
                        "station_id": s,
                        "timestamp": now
                    }
                )
            })
        },
        {
            "id": 5,
            "nombre": "Alerta de Subvoltaje / Throttled en Raspberry Pi",
            "descripcion": "Adquisición, Sensor y Drive OK. Registro de hardware reporta throttled = 0x50000.",
            "diag_esperado": "Throttled",
            "color_esperado": "Amarillo (semi-dark-yellow)",
            "build_fn": lambda s, now: build_scenario_messages(s, now, overrides={
                "health": (
                    f"rsa/seismic/smart/{s}/telemetry/health",
                    {
                        "disk_percent": 45.0,
                        "cpu_temp_c": 50.0,
                        "ram_percent": 28.0,
                        "load_avg_15m": 0.35,
                        "throttled": "0x50000",
                        "timestamp": now
                    }
                )
            })
        },
        {
            "id": 6,
            "nombre": "Alerta de Espacio en Disco Crítico",
            "descripcion": "Adquisición, Sensor y Drive OK. Uso de disco al 89.5% (umbral advertencia > 85%).",
            "diag_esperado": "Disco",
            "color_esperado": "Naranja (dark-orange)",
            "build_fn": lambda s, now: build_scenario_messages(s, now, overrides={
                "health": (
                    f"rsa/seismic/smart/{s}/telemetry/health",
                    {
                        "disk_percent": 89.5,
                        "cpu_temp_c": 49.0,
                        "ram_percent": 28.0,
                        "load_avg_15m": 0.30,
                        "throttled": "0x0",
                        "timestamp": now
                    }
                )
            })
        },
        {
            "id": 7,
            "nombre": "Alerta de Temperatura Elevada en CPU",
            "descripcion": "Adquisición, Sensor y Drive OK. Temperatura térmica de CPU a 78.5 °C (umbral > 70 °C).",
            "diag_esperado": "Temperatura",
            "color_esperado": "Naranja (dark-orange)",
            "build_fn": lambda s, now: build_scenario_messages(s, now, overrides={
                "health": (
                    f"rsa/seismic/smart/{s}/telemetry/health",
                    {
                        "disk_percent": 45.0,
                        "cpu_temp_c": 78.5,
                        "ram_percent": 28.0,
                        "load_avg_15m": 0.95,
                        "throttled": "0x0",
                        "timestamp": now
                    }
                )
            })
        },
        {
            "id": 8,
            "nombre": "Restauración Final a Estado Nominal Limpio",
            "descripcion": "Limpia todas las alertas y restablece la estación a verde nominal.",
            "diag_esperado": "OK",
            "color_esperado": "Verde",
            "build_fn": lambda s, now: build_scenario_messages(s, now)
        }
    ]


def ejecutar_escenario(esc, broker, port, user, password, station_id):
    """Ejecuta un escenario específico publicando la línea base completa + anomalía."""
    now = get_current_iso_time()
    mensajes = esc["build_fn"](station_id, now)

    print("\n" + "=" * 70)
    print(f"▶ EJECUTANDO ESCENARIO {esc['id']}: {esc['nombre']}")
    print("=" * 70)
    print(f"  Estación objetivo   : {station_id}")
    print(f"  Timestamp UTC actual: {now}")
    print(f"  Descripción         : {esc['descripcion']}")
    print(f"  Diagnóstico esper.  : {esc['diag_esperado']}")
    print(f"  Color esperado      : {esc['color_esperado']}")
    print("  Estrategia          : Publicando 5 canales (4 nominales + 1 con error)")
    print("-" * 70)

    ok = publish_mqtt_messages(broker, port, user, password, mensajes)
    if ok:
        print("\n  [✓] 5 tópicos inyectados exitosamente (línea base limpia + anomalía).")
        print(f"  [i] Comprueba en Grafana (SeismicMonitor / Health para '{station_id}'):")
        print(f"      -> Debe mostrar Diagnóstico '{esc['diag_esperado']}' en color {esc['color_esperado']}.")
    else:
        print("\n  [✗] Falló la publicación de mensajes hacia el broker.")
    print("=" * 70 + "\n")


def listar_escenarios(station_id):
    """Muestra un resumen de los escenarios disponibles."""
    escenarios = get_scenarios_meta()
    print("\n" + "=" * 70)
    print("📋 ESCENARIOS DE PRUEBA DISPONIBLES (Estación: " + station_id + ")")
    print("=" * 70)
    for e in escenarios:
        print(f"  [{e['id']}] {e['nombre']}")
        print(f"      Diagnóstico esperado: {e['diag_esperado']} ({e['color_esperado']})")
        print(f"      {e['descripcion']}\n")


def modo_interactivo(broker, port, user, password, station_id):
    """Modo paso a paso interactivo controlado por el operador."""
    escenarios = get_scenarios_meta()
    total = len(escenarios)
    idx = 0

    print("\n" + "=" * 70)
    print("🚀 MODO INTERACTIVO DE SIMULACIÓN - RED SÍSMICA DEL AUSTRO")
    print("=" * 70)
    print(f"Broker: {broker}:{port} | Estación: {station_id}")
    print("Garantía: Cada escenario limpia automáticamente los otros canales a nominal.")
    print("Puedes avanzar escenario a escenario presionando [Enter],")
    print("escribir el número de escenario deseado (1-8), o 'q' para salir.")
    print("=" * 70)

    while idx < total:
        esc = escenarios[idx]
        print(f"\nSiguiente escenario: [{esc['id']}/{total}] - {esc['nombre']}")
        entrada = input("Presiona [Enter] para ejecutar, número de escenario (1-8), o 'q' para salir: ").strip()

        if entrada.lower() in ("q", "quit", "exit"):
            print("\nFinalizando simulador...")
            break
        elif entrada.isdigit():
            num = int(entrada)
            encontrado = next((e for e in escenarios if e["id"] == num), None)
            if encontrado:
                ejecutar_escenario(encontrado, broker, port, user, password, station_id)
                idx = num  # Sugerir el siguiente número
                continue
            else:
                print(f"[!] Escenario '{num}' no existe. Ingresa entre 1 y {total}.")
                continue

        # Ejecutar el escenario actual
        ejecutar_escenario(esc, broker, port, user, password, station_id)
        idx += 1

    print("\n[✓] Sesión interactiva concluida exitosamente. Desconectado del broker.\n")


def main():
    parser = argparse.ArgumentParser(
        description="Simulador de Alertas y Escenarios MQTT para Stack TIG RSA"
    )
    parser.add_argument("-e", "--escenario", type=int, help="Número de escenario específico a ejecutar (1 a 8)")
    parser.add_argument("-l", "--list", action="store_true", help="Listar todos los escenarios disponibles")
    parser.add_argument("-s", "--station", default=DEFAULT_STATION, help=f"ID de estación objetivo (default: {DEFAULT_STATION})")
    parser.add_argument("-b", "--broker", default=DEFAULT_BROKER, help=f"Host del Broker MQTT (default: {DEFAULT_BROKER})")
    parser.add_argument("-p", "--port", type=int, default=DEFAULT_PORT, help=f"Puerto MQTT (default: {DEFAULT_PORT})")
    parser.add_argument("-u", "--user", default=DEFAULT_USER, help=f"Usuario MQTT (default: {DEFAULT_USER})")
    parser.add_argument("-P", "--password", default=DEFAULT_PASS, help="Contraseña MQTT")

    args = parser.parse_args()

    if args.list:
        listar_escenarios(args.station)
        return

    escenarios = get_scenarios_meta()
    if args.escenario is not None:
        esc = next((e for e in escenarios if e["id"] == args.escenario), None)
        if not esc:
            print(f"[ERROR] Escenario {args.escenario} no válido. Usa --list para ver disponibles.")
            sys.exit(1)
        ejecutar_escenario(esc, args.broker, args.port, args.user, args.password, args.station)
    else:
        modo_interactivo(args.broker, args.port, args.user, args.password, args.station)


if __name__ == "__main__":
    main()
