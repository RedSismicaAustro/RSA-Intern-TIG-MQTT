######################################### ~Importaciones~ #############################################
import os
import json
import paho.mqtt.client as mqtt
import time
import random
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv  # pip install python-dotenv

load_dotenv()
mqtt_credentials = {
    "serverAddress": os.getenv("MQTT_BROKER"),
    "username": os.getenv("MQTT_USERNAME"),
    "password": os.getenv("MQTT_PASSWORD"),
}
#######################################################################################################

##################################### ~Variables globales~ ############################################
loggers = {}
temperatura_anterior = 50.0
espacio_libre_anterior = random.uniform(20, 64)
#######################################################################################################

######################################### ~Funciones~ #################################################
def read_fileJSON(nameFile):
    try:
        with open(nameFile, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Archivo {nameFile} no encontrado.")
    except json.JSONDecodeError:
        print(f"Error al decodificar el archivo {nameFile}.")
    return None


def on_connect(client, userdata, flags, rc):
    logger = userdata['logger']
    if rc == 0:
        print("Conectado al broker MQTT con éxito.")
        logger.info("Conectado al broker MQTT con éxito")

        if userdata['is_reconnecting']:
            logger.info("Publicando mensaje de reconexión...")
            estado_online = json.dumps({
                "status": "online",
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            client.publish(userdata['config_mqtt']["topics"]["telemetry_state"], estado_online, qos=1, retain=True)
    else:
        print(f"Error al conectar al broker MQTT. Codigo: {rc}")
        logger.error(f'Error al conectar al broker MQTT. Codigo: {rc}')


def on_disconnect(client, userdata, rc):
    logger = userdata['logger']
    if rc != 0:
        if userdata.get('is_disconnected_logged', False):
            return
        logger.error("Desconexión inesperada del broker MQTT. Código de retorno: %d" % rc)
        userdata['is_disconnected_logged'] = True
    else:
        logger.info("Desconexión limpia del broker MQTT.")
    userdata['is_reconnecting'] = True


def publicar_mensaje(client, topic, id, mensaje):
    mensaje_json = json.dumps({"id": id, "status": mensaje})
    try:
        result = client.publish(topic, mensaje_json)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise Exception(f"Error al publicar en MQTT. Código de error: {result.rc}")
        logger = client._userdata['logger']
        logger.info(f"Mensaje publicado exitosamente en el tópico {topic}: {mensaje_json}")
    except Exception as e:
        logger = client._userdata['logger']
        logger.error(f"Error al intentar publicar en el tópico {topic}. Detalle del error: {e}")


def iniciar_cliente_mqtt(config_mqtt, dispositivo_id, logger):
    client = mqtt.Client(userdata={'config_mqtt': mqtt_credentials, 'dispositivo_id': dispositivo_id, 'is_reconnecting': False, 'logger': logger})
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    lwt_message = json.dumps({
        "status": "offline",
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    lwt_topic = config_mqtt["topics"]["telemetry_state"]
    client.will_set(lwt_topic, payload=lwt_message, qos=1, retain=True)

    try:
        client.username_pw_set(mqtt_credentials["username"], mqtt_credentials["password"])
        client.connect(mqtt_credentials["serverAddress"], 1883, 60)

        estado_on = json.dumps({
            "status": "on",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        client.publish(config_mqtt["topics"]["telemetry_state"], estado_on, qos=1, retain=True)
        client.loop_start()
    except Exception as e:
        logger.error(f"Error al conectar o publicar en el broker MQTT: {e}")
    return client


def obtener_logger(id_estacion, log_directory, log_filename):
    global loggers
    if id_estacion not in loggers:
        logger = logging.getLogger(id_estacion)
        logger.setLevel(logging.DEBUG)
        log_path = os.path.join(log_directory, log_filename)
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        loggers[id_estacion] = logger
    return loggers[id_estacion]


def obtener_uptime():
    try:
        with open("/proc/uptime", "r") as f:
            uptime_total = float(f.read().split()[0])
        return int(uptime_total)
    except Exception:
        return 0


def publicar_datos_telemetria(client, config_mqtt, dispositivo_id):
    temperatura_celsius = round(random.uniform(40, 60), 1)
    disk_free_gb = round(random.uniform(1, 64), 1)
    payload_telemetria = {
        "id": dispositivo_id,
        "uptime_s": obtener_uptime(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "temp": temperatura_celsius,
        "disk_free_gb": disk_free_gb,
        "status": "on"
    }
    topic = config_mqtt.get("topicTelemetry", "telemetry/NOM00/data")
    client.publish(topic, json.dumps(payload_telemetria))


def publicar_datos_health(client, config_mqtt, dispositivo_id):
    temp_cpu = round(random.uniform(40, 60), 1)
    disk_free_gb = round(random.uniform(1, 64), 1)
    uptime_s = obtener_uptime()

    payload_health = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "temp_cpu": temp_cpu,
        "disk_free_gb": disk_free_gb,
        "uptime_s": uptime_s
    }

    topic_template = config_mqtt["topics"]["telemetry_health"]
    topic = topic_template.format(
        org=config_mqtt.get("org", "rsa"),
        app=config_mqtt.get("app", "seismic"),
        cap=config_mqtt.get("cap", "smart"),
        id=dispositivo_id
    )

    result = client.publish(topic, json.dumps(payload_health), qos=1, retain=False)
    logger = client._userdata['logger']
    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        logger.info(f"Publicado telemetry_health en {topic}: {payload_health}")
    else:
        logger.error(f"Error al publicar telemetry_health en {topic}: {result.rc}")


def publicar_heartbeat(client, config_mqtt, dispositivo_id, last_event_time):
    topic = config_mqtt["topics"]["telemetry_heartbeat"]
    payload = {
        "last_event": last_event_time.isoformat(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    client.publish(topic, json.dumps(payload), qos=1, retain=True)


def obtener_timestamp_iso():
    return datetime.now(timezone.utc).isoformat()


def simular_evento_sismico():
    if random.random() < 0.1:  # 10% de probabilidad
        return {
            "event_id": f"evt_{int(time.time())}",
            "timestamp": obtener_timestamp_iso(),
            "amplitude": round(random.uniform(0.1, 5.0), 2),
            "confidence": round(random.uniform(0.6, 0.99), 2)
        }
    return None
#######################################################################################################

############################################# ~Main~ ###################################################
def main():
    config_mqtt_file = "../../config/configuracion_mqtt.json"
    config_dispositivo_file = "../../config/configuracion_dispositivo.json"
    log_directory = "../../log-files"

    config_mqtt = read_fileJSON(config_mqtt_file)
    if config_mqtt is None:
        print("No se pudo leer configuración MQTT.")
        return

    config_dispositivo = read_fileJSON(config_dispositivo_file)
    if config_dispositivo is None:
        print("No se pudo leer configuración del dispositivo.")
        return

    dispositivo_id = config_dispositivo.get("dispositivo", {}).get("id", "Unknown")
    logger = obtener_logger(dispositivo_id, log_directory, "mqtt.log")
    client = iniciar_cliente_mqtt(config_mqtt, dispositivo_id, logger)

    contador_health = 0
    ultima_publicacion_heartbeat = time.time()
    last_event_time = datetime.now(timezone.utc)

    try:
        while True:
            time.sleep(1)
            publicar_datos_telemetria(client, config_mqtt, dispositivo_id)

            contador_health += 1
            if contador_health >= 10:
                publicar_datos_health(client, config_mqtt, dispositivo_id)
                contador_health = 0

            # Simulación de evento sísmico
            evento = simular_evento_sismico()
            if evento:
                last_event_time = datetime.now(timezone.utc)
                topic_evento = config_mqtt["topics"].get("events_detected", "rsa/seismic/smart/NOM00/events/detected")
                client.publish(topic_evento, json.dumps(evento), qos=1, retain=False)
                logger.info(f"Evento sísmico detectado: {evento}")


            # Heartbeat cada 60 segundos
            if time.time() - ultima_publicacion_heartbeat >= 60:
                publicar_heartbeat(client, config_mqtt, dispositivo_id, last_event_time)
                ultima_publicacion_heartbeat = time.time()

    except KeyboardInterrupt:
        print("Finalizando cliente MQTT...")
        if client:
            estado_offline = json.dumps({
                "status": "offline",
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            client.publish(config_mqtt["topics"]["telemetry_state"], estado_offline, qos=1, retain=True)
            client.loop_stop()
            client.disconnect()
            print("Cliente MQTT finalizado correctamente.")
#######################################################################################################

if __name__ == '__main__':
    main()
#######################################################################################################
