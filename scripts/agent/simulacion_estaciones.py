import os
import json
import threading
import time
import random
from datetime import datetime, timezone
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

# ================================
# Cargar credenciales MQTT
# ================================
load_dotenv()
mqtt_credentials = {
    "serverAddress": os.getenv("MQTT_BROKER"),
    "username": os.getenv("MQTT_USERNAME"),
    "password": os.getenv("MQTT_PASSWORD"),
}

# ================================
# Utilidades JSON
# ================================
def cargar_json(ruta):
    with open(ruta, "r") as f:
        return json.load(f)

def guardar_json(ruta, contenido):
    with open(ruta, "w") as f:
        json.dump(contenido, f, indent=4)

# ================================
# GENERAR CONFIGS MQTT
# ================================
def generar_configs(estaciones):
    base_mqtt = cargar_json("../../config/configuracion_mqtt.json")
    base_disp = cargar_json("../../config/configuracion_dispositivo.json")

    for est in estaciones:
        mqtt_copy = json.loads(json.dumps(base_mqtt))
        disp_copy = json.loads(json.dumps(base_disp))

        disp_copy["dispositivo"]["id"] = est

        mqtt_copy["topics"] = {
            "telemetry_state":    f"rsa/seismic/smart/{est}/telemetry/state",
            "telemetry_health":   f"rsa/seismic/smart/{est}/telemetry/health",
            "telemetry_heartbeat":f"rsa/seismic/smart/{est}/telemetry/heartbeat",
            "events_detected":    f"rsa/seismic/smart/{est}/events/detected",
            "events_data":        f"rsa/seismic/smart/{est}/events/data"
        }

        guardar_json(f"../../config/configuracion_mqtt_{est}.json", mqtt_copy)
        guardar_json(f"../../config/configuracion_dispositivo_{est}.json", disp_copy)

# ================================
# SIMULACIÓN POR ESTACIÓN
# ================================
def mqtt_loop(config_mqtt, config_disp):

    est = config_disp["dispositivo"]["id"]
    topics = config_mqtt["topics"]

    client = mqtt.Client()
    client.username_pw_set(mqtt_credentials["username"], mqtt_credentials["password"])
    client.connect(mqtt_credentials["serverAddress"], 1883, 60)
    client.loop_start()

    print(f"🔥 Iniciando simulador de estación: {est}")

    while True:

        now = datetime.now(timezone.utc).isoformat()

        # STATE
        client.publish(topics["telemetry_state"], json.dumps({
            "id": est,
            "status": "online",
            "timestamp": now
        }))

        # HEALTH
        client.publish(topics["telemetry_health"], json.dumps({
            "temperature": random.uniform(40, 60),
            "disk_free_gb": random.uniform(10, 64),
            "timestamp": now
        }))

        # HEARTBEAT
        client.publish(topics["telemetry_heartbeat"], json.dumps({
            "heartbeat": True,
            "timestamp": now
        }))

        # EVENT DETECTED (aleatorio)
        if random.random() < 0.05:
            client.publish(topics["events_detected"], json.dumps({
                "id": est,
                "event": "threshold_exceeded",
                "timestamp": now
            }))

        # EVENT DATA (si lo necesitas)
        client.publish(topics["events_data"], json.dumps({
            "id": est,
            "waveform": [random.randint(-500, 500) for _ in range(10)],
            "timestamp": now
        }))

        time.sleep(1)

# ================================
# MAIN
# ================================
def main():

    estaciones = ["NOM00", "NOM01"]

    print("✔ Generando archivos de configuración base...")
    generar_configs(estaciones)

    hilos = []
    for est in estaciones:
        mqtt_cfg = cargar_json(f"../../config/configuracion_mqtt_{est}.json")
        disp_cfg = cargar_json(f"../../config/configuracion_dispositivo_{est}.json")

        hilo = threading.Thread(target=mqtt_loop, args=(mqtt_cfg, disp_cfg))
        hilo.start()
        hilos.append(hilo)

    for h in hilos:
        h.join()


if __name__ == "__main__":
    main()
