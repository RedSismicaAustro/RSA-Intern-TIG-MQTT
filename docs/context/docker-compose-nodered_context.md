---
proyecto: RSA-Intern-TIG-MQTT
tipo: contexto_tecnico
archivo: services/node-red/docker-compose.yml
temas: [docker-compose, node-red, automation, panel-control, mqtt, ui-dashboard]
---
# Docker Compose Node-RED y Archivos Asociados — Contexto para Agentes IA

> Orquestación y lógica del panel de control y automatización remota basado en Node-RED para el envío de comandos de extracción de eventos y monitoreo de respuestas de la red acelerográfica.

**Ruta**: `services/node-red/docker-compose.yml`
**Rutas de Archivos Asociados**:
- Flujos de Node-RED: `services/node-red/flows.json`
- Configuración de Node-RED: `services/node-red/settings.js`
- Dependencias del Panel: `services/node-red/package.json`

**LOC**: `docker-compose.yml`: 20 | `flows.json`: 680 | `settings.js`: 96 | `package.json`: 8
**Lenguaje/Formato**: YAML (Docker Compose), JSON (Flows & npm Package), JavaScript (CommonJS Settings)
**Dependencias/Imágenes**: `nodered/node-red:latest` (Imagen Docker) | `node-red-dashboard` (~3.6.6, dependencias npm)
**Proceso**: Contenedor Docker persistente administrado por Docker Compose, integrado en la red externa `rsa_network` para su comunicación.

---

## Arquitectura / Estructura de Servicios

El panel de control remoto opera como una consola web interactiva conectada al broker MQTT del proyecto. Su funcionamiento se define en dos flujos principales:

1. **Flujo de Salida (Construcción y Envío de Comandos)**:
   - El operador selecciona los parámetros en el formulario visual (Estación, Fecha, Hora de inicio, Duración y switch para subir a Google Drive).
   - Al presionar **"Enviar Comando"**, un nodo de función valida los campos, unifica la fecha y la hora en formato ISO (`YYYY-MM-DDZHH:MM:SS`), genera un identificador de petición único (`request_id`) y publica un mensaje JSON en el tópico `rsa/seismic/smart/{target_id}/cmd/extract_event` (QoS 1).
2. **Flujo de Entrada (Recepción y Log de Respuestas)**:
   - Node-RED se suscribe al tópico `rsa/seismic/smart/+/cmd/extract_event/res` para recibir las respuestas de estado de las estaciones.
   - Las respuestas se parsean en un nodo de función que extrae el identificador de la estación, evalúa el estado (`completed`/`error`), asigna formato HTML y color a la notificación, y añade el registro a un historial en memoria (`flow.responseHistory`) con límite de 50 entradas.
   - Finalmente, se envía un mensaje emergente tipo toast (`ui_toast`) al navegador y se actualiza el feed de registro HTML (`ui_template`) en el panel.

```mermaid
graph TD
    subgraph Navegador del Operador (Puerto 1880)
        UI[Node-RED Dashboard UI] -->|1. Configura & Envía| CmdBtn[Botón: Enviar Comando]
        Toast[ui_toast: Emergente Toast] -.->|Notificación Visual| UI
        LogPanel[ui_template: Historial HTML] -.->|Feed de Bitácora| UI
    end

    subgraph Docker Container: rsa-nodered
        CmdBtn -->|2. Evento de Click| Build[Funcion: Build Command]
        Build -->|3. Serializa JSON| MqttOut[MQTT Out Node]
        MqttIn[MQTT In Node] -->|5. Recibe Respuesta| Parse[Funcion: Parse Response]
        Parse -->|6a. Emite Toast| Toast
        Parse -->|6b. Actualiza Historial| LogPanel
    end

    MqttOut -->|4a. CMD: extract_event| Broker[MQTT Broker]
    Broker -->|4b. RES: extract_event/res| MqttIn

    Broker -.->|Envía Comando / Recibe Respuesta| Estaciones[Estaciones Acelerográficas]
```

---

## Configuraciones / Variables de Entorno

### Variables del Entorno Docker (`docker-compose.yml`)
- `TZ=America/Guayaquil`: Zona horaria para asegurar la concordancia de logs y eventos temporales locales.

### Puertos Expuestos
- `1880:1880`: Puerto nativo para acceder al editor de Node-RED (ruta `/admin`) y a la interfaz del Dashboard (ruta `/ui`).

### Volúmenes de Persistencia
- `/home/rsa/data/nodered:/data`: Mapea la carpeta del host al contenedor para persistir configuraciones, flujos, credenciales y logs.

### Ajustes del Editor y Motor (`settings.js`)
- `flowFile`: Configurado a `'flows.json'` para forzar a Node-RED a utilizar el archivo que se encuentra versionado en el repositorio de Git.
- `credentialSecret: false`: Deshabilita el cifrado del archivo de credenciales `flows_cred.json`, permitiendo inicializar credenciales (ej. passwords del MQTT Broker) en texto plano de forma reproducible para el despliegue automático del stack.
- `logging`: Define dos flujos de log con nivel `info`: consola estándar y archivo persistente `/data/nodered.log`.
- `editorTheme`: Personaliza el título de la página a `"RSA — Control Sísmico"` y el título de cabecera a `"RSA Seismic Network"`.
- `mqttReconnectTime: 15000`: Temporizador de reconexión al broker MQTT establecido en 15 segundos para tolerancia a caídas de red.

---

## Componentes / Elementos Clave

### Dependencias del Panel (`package.json`)
Contiene la configuración del paquete npm local e integra la dependencia `"node-red-dashboard": "~3.6.6"`, requerida para renderizar los elementos gráficos de control.

### Nodos Clave en los Flujos (`flows.json`)

| ID del Nodo | Tipo de Nodo | Propósito / Función en el Flujo |
|-------------|--------------|---------------------------------|
| `rsa-tab-control` | `tab` | Pestaña contenedora de toda la lógica del panel remoto. |
| `rsa-mqtt-broker` | `mqtt-broker` | Define la conexión MQTT utilizando la variable de entorno `${MQTT_BROKER}` en el puerto 1883 sin TLS. ClientID: `nodered-rsa-control`. |
| `node-target-id` | `ui_dropdown` | Dropdown visual para seleccionar el destinatario del comando (`broadcast` o ID de estación individual: `DEV00`, `DEV01`, `CHA01`, `CHA02`, `TEN01`). |
| `node-build-command` | `function` | Motor matemático que combina la fecha y hora seleccionada (gestionando la hora en milisegundos), formatea el timestamp a ISO `YYYY-MM-DDZHH:MM:SS`, genera un `request_id` dinámico e inyecta la cabecera MQTT. |
| `node-mqtt-out` | `mqtt out` | Publica el comando en el tópico dinámico de control con QoS 1. |
| `node-mqtt-in` | `mqtt in` | Se suscribe a `rsa/seismic/smart/+/cmd/extract_event/res` con QoS 1 para capturar respuestas. |
| `node-parse-response` | `function` | Procesa las respuestas de la estación, genera la notificación visual con código de colores (verde para `completed`, rojo para `error`) y gestiona la pila del historial en memoria. |
| `94db4fbc4528f423` | `ui_template` | Nodo template HTML/Angular que renderiza el historial de respuestas dentro de un contenedor scrollable con tipografía monospace. |

---

## Limitaciones Conocidas / TODOs

- **Cero Autenticación**: El dashboard web expuesto en el puerto 1880 no posee configurado el middleware de autenticación (ej. adminauth en `settings.js`). Cualquier usuario en la red interna o externa con acceso al puerto puede enviar comandos o editar los flujos. Se recomienda implementar autenticación HTTP básica o token en entornos productivos.
- **Sin Cifrado MQTT**: La comunicación con el Broker se realiza a través de TCP básico (puerto 1883) sin TLS. Las credenciales viajan en texto plano.
- **Historial en Memoria Volátil**: El historial de respuestas mostrado en la interfaz se almacena en el contexto de flujo (`flow.responseHistory`) en memoria volátil. Si el contenedor se reinicia o se redespliega, el historial de respuestas se perderá.
- **Seguridad en Credenciales**: Dado que `credentialSecret` está deshabilitado para facilitar el despliegue, el archivo `/home/rsa/data/nodered/flows_cred.json` contiene contraseñas de MQTT en texto plano. Este archivo debe mantenerse estrictamente bajo `.gitignore` y protegerse con permisos de lectura limitados en el host.
