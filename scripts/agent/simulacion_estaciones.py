import os
import json
import threading
import time
import random
import logging
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

loggers = {}

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
# LOGGER POR ESTACIÓN
# ================================
def obtener_logger(id_estacion):
    global loggers
    if id_estacion not in loggers:
        logger = logging.getLogger(id_estacion)
        logger.setLevel(logging.DEBUG)

        if not os.path.exists("../../log-files"):
            os.makedirs("../../log-files")

        path = f"../../log-files/{id_estacion}.log"
        handler = logging.FileHandler(path)
        handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
        logger.addHandler(handler)

        loggers[id_estacion] = logger
    return loggers[id_estacion]


# ================================
# FUNCIONES DEL CÓDIGO ORIGINAL
# ================================
def on_connect(client, userdata, flags, rc):
    logger = userdata["logger"]
    est = userdata["id"]

    if rc == 0:
        logger.info(f"[{est}] Conectado al broker.")

        estado_online = json.dumps({
            "status": "online",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        client.publish(userdata["topics"]["telemetry_state"], estado_online, qos=1, retain=True)
    else:
        logger.error(f"[{est}] Error al conectar. Código {rc}")


def on_disconnect(client, userdata, rc):
    logger = userdata["logger"]
    est = userdata["id"]

    if rc != 0:
        logger.error(f"[{est}] Desconexión inesperada.")
    else:
        logger.info(f"[{est}] Desconexión limpia.")


def obtener_uptime():
    try:
        with open("/proc/uptime", "r") as f:
            return int(float(f.read().split()[0]))
    except:
        return random.randint(1, 50000)


def publicar_mensaje(client, topics, topic_key, payload, logger):
    topic = topics.get(topic_key)
    if not topic:
        logger.error(f"Tópico {topic_key} NO existe en la config.")
        return

    client.publish(topic, json.dumps(payload), qos=1, retain=False)
    logger.info(f"Publicado en {topic}: {payload}")


def publicar_datos_telemetria(client, topics, est, logger):
    payload = {
        "id": est,
        "uptime_s": obtener_uptime(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "temp": round(random.uniform(40, 60), 1),
        "disk_free_gb": round(random.uniform(1, 64), 1),
        "status": "on"
    }

    client.publish(topics["telemetry_state"], json.dumps(payload))
    logger.info(f"[{est}] Telemetría enviada.")


def publicar_datos_health(client, topics, est, logger):
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "temp_cpu": round(random.uniform(40, 60), 1),
        "disk_free_gb": round(random.uniform(10, 64), 1),
        "uptime_s": obtener_uptime()
    }

    client.publish(topics["telemetry_health"], json.dumps(payload), qos=1)
    logger.info(f"[{est}] Health enviado.")


def publicar_heartbeat(client, topics, last_event, logger):
    payload = {
        "last_event": last_event.isoformat(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    client.publish(topics["telemetry_heartbeat"], json.dumps(payload), qos=1, retain=True)
    logger.info("Heartbeat enviado.")


def simular_evento_sismico():
    if random.random() < 0.1:
        return {
            "event_id": f"evt_{int(time.time())}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "amplitude": round(random.uniform(0.1, 5.0), 2),
            "confidence": round(random.uniform(0.6, 0.99), 2)
        }
    return None


# ================================
# LOOP MQTT POR ESTACIÓN
# ================================
def mqtt_loop(config_mqtt, config_disp):

    est = config_disp["dispositivo"]["id"]
    topics = config_mqtt["topics"]
    logger = obtener_logger(est)

    client = mqtt.Client(userdata={
        "logger": logger,
        "id": est,
        "topics": topics
    })

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    # LWT
    lwt_message = json.dumps({"status": "offline", "timestamp": datetime.now(timezone.utc).isoformat()})
    client.will_set(topics["telemetry_state"], payload=lwt_message, qos=1, retain=True)

    client.username_pw_set(mqtt_credentials["username"], mqtt_credentials["password"])
    client.connect(mqtt_credentials["serverAddress"], 1883)
    client.loop_start()

    logger.info(f"Estación {est} iniciada.")

    contador_health = 0
    last_event_time = datetime.now(timezone.utc)
    last_heartbeat = time.time()

    while True:

        # TELEMETRÍA (cada 1s)
        publicar_datos_telemetria(client, topics, est, logger)

        # HEALTH (cada 10s)
        contador_health += 1
        if contador_health >= 10:
            publicar_datos_health(client, topics, est, logger)
            contador_health = 0

        # EVENTO SÍSMICO
        evento = simular_evento_sismico()
        if evento:
            last_event_time = datetime.now(timezone.utc)
            publicar_mensaje(client, topics, "events_detected", evento, logger)

        # HEARTBEAT (cada 60s)
        if time.time() - last_heartbeat >= 60:
            publicar_heartbeat(client, topics, last_event_time, logger)
            last_heartbeat = time.time()

        time.sleep(1)


# ================================
# MAIN
# ================================
def main():

    estaciones = ["NOM00", "NOM01"]

    for est in estaciones:
        mqtt_cfg = cargar_json(f"../../config/configuracion_mqtt_{est}.json")
        disp_cfg = cargar_json(f"../../config/configuracion_dispositivo_{est}.json")

        hilo = threading.Thread(target=mqtt_loop, args=(mqtt_cfg, disp_cfg))
        hilo.start()


if __name__ == "__main__":
    main()
