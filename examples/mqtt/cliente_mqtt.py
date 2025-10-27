######################################### ~Funciones~ #################################################
import os
import json
import paho.mqtt.client as mqtt
import time
import random
import logging
from datetime import datetime
import os
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
#######################################################################################################

######################################### ~Funciones~ #################################################
# Funcion para leer el archivo de configuracion JSON
def read_fileJSON(nameFile):
    try:
        with open(nameFile, 'r') as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        print(f"Archivo {nameFile} no encontrado.")
        return None
    except json.JSONDecodeError:
        print(f"Error al decodificar el archivo {nameFile}.")
        return None

# Función que se llama cuando el cliente se conecta al broker
def on_connect(client, userdata, flags, rc):
    logger = userdata['logger']
    if rc == 0:
        print("Conectado al broker MQTT con éxito.")
        logger.info("Conectado al broker MQTT con éxito")
        # Publicar mensaje "online" cuando se reconecta
        if userdata['is_reconnecting']:
            logger.info("Publicando mensaje de reconexión...")
            publicar_mensaje(client, userdata['config_mqtt']["topicStatus"], userdata['dispositivo_id'], "online")
            userdata['is_reconnecting'] = False
    else:
        print(f"Error al conectar al broker MQTT. Codigo: {rc}")
        logger.error(f'Error al conectar al broker MQTT. Codigo: {rc}')

# Función que se llama cuando el cliente se desconecta del broker
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

# Función para publicar mensajes por MQTT en formato JSON
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

# Función para iniciar el cliente MQTT
def iniciar_cliente_mqtt(config_mqtt, dispositivo_id, logger):
    client = mqtt.Client(userdata={'config_mqtt': mqtt_credentials, 'dispositivo_id': dispositivo_id, 'is_reconnecting': False, 'logger': logger})
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    # Crear el mensaje LWT en formato JSON
    lwt_message = json.dumps({"id": dispositivo_id, "status": "offline"})
    lwt_topic = "status"  # Tópico LWT para notificar desconexiones

    # Establecer Last Will and Testament (LWT)
    client.will_set(lwt_topic, payload=lwt_message, qos=1, retain=False)
    
    try:
        client.username_pw_set(mqtt_credentials["username"], mqtt_credentials["password"])
        client.connect(mqtt_credentials["serverAddress"], 1883, 60)

        # Publicar mensaje de inicio
        publicar_mensaje(client, config_mqtt["topicStatus"], dispositivo_id, "on")

        client.loop_start()

    except mqtt.MQTTException as e:
        logger.error(f"Error relacionado con MQTT: {e}")
    except Exception as e:
        logger.error(f"Error general al conectar o publicar en el broker MQTT: {e}")
    return client
# Función para inicializar y obtener el logger de un cliente
def obtener_logger(id_estacion, log_directory, log_filename):
    global loggers
    if id_estacion not in loggers:
        # Crear un logger para el cliente
        logger = logging.getLogger(id_estacion)
        logger.setLevel(logging.DEBUG)
        # Ruta completa del archivo de log
        log_path = os.path.join(log_directory, log_filename)
        # Crear manejador de archivo, apuntando al archivo existente
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(logging.DEBUG)
        # Crear formato de logging y añadirlo al manejador
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        # Añadir el manejador al logger
        logger.addHandler(file_handler)
        loggers[id_estacion] = logger
    return loggers[id_estacion]

# Función para obtener valor de uptime
def obtener_uptime():
    try:
        with open("/proc/uptime", "r") as f:
            uptime_total = float(f.read().split()[0])  # Primer valor es uptime en segundos
        return int(uptime_total)
    except Exception:
        return 0  # Si falla, retorna 0


# Función para publicar datos de telemetría
def publicar_datos_telemetria(client, config_mqtt, dispositivo_id):
    # Leer el tópico de telemetría
    topicotelemetria = config_mqtt.get("topicTelemetry")
    # Datos simulados
    # Dato de temperatura
    temperatura_celsius = random.uniform(40, 60),  # temperatura entre 40°C y 60°C
    # Dato de espacio de disco (GB)
    disk_free_gb = random.uniform(1, 64),  # Espacio entre 1 y 64 GB
    # Datos a enviar
    payload_telemetria = {
    "id": dispositivo_id,
    "uptime_s": obtener_uptime(),     # uptime
    "timestamp": datetime.now().isoformat(), #Last event
    "temp": temperatura_celsius,
    "disk_free_gb": disk_free_gb,
    "status": "on"
    }
    # Convertir el diccionario a texto JSON
    payload_telemetria_str = json.dumps(payload_telemetria)  
    # Publicar el mensaje
    result_te = client.publish(topicotelemetria, payload_telemetria_str)


## Función para obtener la temperatura
#def obtener_temp():
#    try:
#        # Abrir archivo de temperatura
#        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
#            #Leer y convertir a entero, el valor esta escalado por mil
#            temp_sim_mil = int(f.read().strip())
#        temp_sim = temp_sim_mil / 1000
#        return temp_sim
#    except Exception:
#        return 0  # si falla, retorna temperatura 0

# Función para publicar datos simulados del pc
#def publicar_datos_simulados(client, config_mqtt, dispositivo_id):
#    topicodatossim = config_mqtt.get("topicVariablespc")
#    #temperatura_celsius_sim = obtener_temp()
#        # Rango de valores simulados
#    temperatura_celsius = random.uniform(40, 60)  # temperatura entre 40°C y 60°C
#    disk_free_gb = random.uniform(10, 100)       # disco libre entre 10 y 100 GB
#     # Datos a enviar
#    payload_datos_sim = {
#    "id": dispositivo_id,
#    "timestamp": datetime.now().isoformat(),
#    "temp": temperatura_celsius,
#    "disk_free": disk_free_gb  
#    # Convertir el diccionario a texto JSON
#    payload_datos_sim__str = json.dumps(payload_datos_sim)  
#    # Publicar el mensaje
#    result_datos_sim = client.publish(topicodatossim, payload_datos_sim__str)


# Función para obtener datos simulados del PC
def obtener_datos_simulados(dispositivo_id, config_mqtt):



    # Construir payload
    payload = {
        "id": dispositivo_id,
        "timestamp": datetime.now().isoformat(),
        "temp": random.uniform(40, 60),  # temperatura entre 40°C y 60°C
        "disk_free_gb": round(disk_free_gb, 1),
        "status": "on"
    }

    # Publicar en el tópico de telemetría
    topic = config_mqtt.get("topicTelemetry", "telemetry/NOM00/data")
    return topic, json.dumps(payload)


#######################################################################################################

############################################# ~Main~ ###################################################
def main():


    config_mqtt_file = "../../config/configuracion_mqtt.json"
    config_dispositivo_file = "../../config/configuracion_dispositivo.json"
    log_directory = "../../log-files"

    
    # Lee el archivo de configuración MQTT
    config_mqtt = read_fileJSON(config_mqtt_file)
    if config_mqtt is None:
        print("No se pudo leer el archivo de configuración. Terminando el programa.")
        return
    
    # Lee el archivo de configuración del dispositivo
    config_dispositivo = read_fileJSON(config_dispositivo_file)
    if config_dispositivo is None:
        print("No se pudo leer el archivo de configuración del dispositivo. Terminando el programa.")
        return

    # Obtiene el ID del dispositivo
    dispositivo_id = config_dispositivo.get("dispositivo", {}).get("id", "Unknown")

    # Inicializa el logger
    logger = obtener_logger(dispositivo_id, log_directory, "mqtt.log")

    client = None

    try:
        # Inicia el cliente mqtt
        client = iniciar_cliente_mqtt(config_mqtt, dispositivo_id, logger)
        # Loop principal
      
        while True:
            time.sleep(1)
            # Publicar datos telemetría
            publicar_datos_telemetria(client, config_mqtt, dispositivo_id)

            # Publicar datos simulados
            #publicar_datos_simulados(client, config_mqtt, dispositivo_id)

            time.sleep(5)  # Esperar 5 segundos
    except KeyboardInterrupt:
        print("Finalizando cliente MQTT...")
        if client:
            # Al finalizar cliente, asegurar que el estado sea apagado: offline
            publicar_mensaje(client, config_mqtt["topicStatus"], dispositivo_id, "offline")
            client.loop_stop()
            client.disconnect()
            print("Cliente MQTT finalizado correctamente.")



#######################################################################################################
if __name__ == '__main__':
    main()

#######################################################################################################

#######################################################################################################

