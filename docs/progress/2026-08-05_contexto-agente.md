# Resumen de Sesión: Despliegue en Nuevo Servidor Ubuntu 22.04 y Parametrización de Volúmenes Docker

**Fecha**: 2026-08-05  
**Repositorio**: `RSA-Intern-TIG-MQTT`  
**Agente de IA**: Antigravity (Google DeepMind)  
**Usuario**: Milton / parmont / RSA  

---

## 🎯 Objetivo de la Sesión

Desplegar, depurar e integrar el stack completo de monitoreo sísmico (`RSA-Intern-TIG-MQTT`) en un nuevo servidor **Ubuntu 22.04.5 LTS** (`192.168.10.200`). Se realizó la parametrización de rutas de volúmenes Docker (`DATA_DIR` y `DRIVE_DIR`), la corrección de permisos de usuario host en volúmenes persistentes, la resolución de conflictos de puertos/colisiones MQTT y la identificación del procedimiento de habilitación del paquete `node-red-dashboard`.

---

## 📂 Archivos Creados y Modificados

```text
montajes/ubuntu-server/rsa/RSA-Intern-TIG-MQTT/
├── docs/
│   └── progress/
│       └── 2026-08-05_contexto-agente.md             [NUEVO] Este documento de transición técnica
│
├── services/
│   ├── docker-unified/
│   │   ├── .env.example                              [MODIFICADO] Adición de variables de rutas base (DATA_DIR, DRIVE_DIR)
│   │   └── docker-compose.yml                        [MODIFICADO] Parametrización de volúmenes de InfluxDB, Grafana y Event Analyzer
│   └── node-red/
│       └── docker-compose.yml                        [MODIFICADO] Parametrización de volumen de Node-RED con DATA_DIR
```

---

## ⚙️ Configuración del Entorno y Despliegue

### 1. Diagnóstico del Entorno del Servidor
* **Sistema Operativo**: Ubuntu 22.04.5 LTS (GNU/Linux 5.15.0-185-generic x86_64).
* **Motor de Contenedores**: Docker Engine 29.7.1 y Docker Compose v5.3.1 (Servicio `docker.service` activo).
* **Dirección IP en Red Local**: `192.168.10.200`.

### 2. Parametrización de Rutas de Volúmenes (`DATA_DIR` / `DRIVE_DIR`)
Para desacoplar el proyecto del nombre del usuario host (`/home/rsa/` vs `/home/parmont/`) y permitir el despliegue en cualquier servidor de forma portátil:
* Se reemplazaron las rutas hardcodeadas en `docker-compose.yml` por variables de entorno:
  - `${DATA_DIR}` $\rightarrow$ `/home/parmont/data` (datos persistentes de InfluxDB, Grafana y Node-RED).
  - `${DRIVE_DIR}` $\rightarrow$ `/home/parmont/datos_estaciones_drive` (punto de montaje de trazas MiniSEED en Google Drive).
* Se actualizó `services/docker-unified/.env.example` registrando los valores por defecto del proyecto.

### 3. Resolución de Permisos de Volúmenes Host
Se corrigió la falla de permisos que impedía el inicio de Grafana y Node-RED asignando los UIDs propietarios oficiales:
* **Grafana (UID 472)**: `sudo chown -R 472:472 /home/parmont/data/grafana`
* **Node-RED (UID 1000)**: `sudo chown -R 1000:1000 /home/parmont/data/nodered`

---

## 🛠️ Estado de Verificación de Servicios (`192.168.10.200`)

Todos los servicios principales han quedado desplegados, activos y accesibles desde la red local:

| Servicio | Estado | URL / Puerto |
| :--- | :--- | :--- |
| **Grafana** | `Up` | `http://192.168.10.200:3000` |
| **Node-RED (Dashboard & Editor)** | `Up` | `http://192.168.10.200:1880/ui` & `http://192.168.10.200:1880/` |
| **Event Analyzer (Streamlit)** | `Up` | `http://192.168.10.200:8501` |
| **InfluxDB v2** | `Up (Healthy)` | `http://192.168.10.200:8086` |
| **Correlador MQTT** | `Up` | *Daemon interno en red Docker* |

---

## 📋 Pasos Sugeridos para el Siguiente Agente

1. **Instalar `node-red-dashboard` en Node-RED**:
   - Abrir `http://192.168.10.200:1880/` $\rightarrow$ Menú `☰` $\rightarrow$ **Manage palette** $\rightarrow$ **Install** $\rightarrow$ buscar `node-red-dashboard` e instalar.
   - Alternativamente, ejecutar: `docker exec -it rsa-nodered npm install --prefix /data node-red-dashboard` y reiniciar el contenedor.
2. **Montaje de Google Drive para Event Analyzer**:
   - Configurar el montaje de `rclone` en la ruta `/home/parmont/datos_estaciones_drive` para permitir a `event-analyzer` (`:8501`) escanear e indexar los archivos MiniSEED de la red.
3. **Prueba de Comandos Broadcast MQTT**:
   - Acceder al panel de Node-RED en `http://192.168.10.200:1880/ui`, configurar una orden de extracción manual y verificar la recepción en las estaciones acelerográficas.
