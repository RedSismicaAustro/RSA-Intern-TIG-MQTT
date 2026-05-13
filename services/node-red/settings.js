/**
 * settings.js — Configuración de Node-RED
 * RSA Seismic Network — Panel de Control Remoto
 *
 * Este archivo se monta en el contenedor en: /data/settings.js
 * El archivo /data/flows_cred.json contiene las credenciales del broker MQTT.
 * NUNCA commitear flows_cred.json (está en .gitignore).
 */

module.exports = {

    // =========================================================================
    // Archivo de flujos principal (versionado en Git)
    // =========================================================================
    flowFile: 'flows.json',

    // =========================================================================
    // Credenciales: credentialSecret: false → almacenamiento en texto plano.
    // Esto permite leer flows_cred.json sin cifrado, facilitando el despliegue
    // reproducible mediante variables de entorno o archivos estáticos.
    // =========================================================================
    credentialSecret: false,

    // =========================================================================
    // Puerto del editor y dashboard (1880 mapeado en docker-compose.yml)
    // =========================================================================
    uiPort: process.env.PORT || 1880,

    // =========================================================================
    // Logging: consola + archivo en /data/nodered.log
    // =========================================================================
    logging: {
        console: {
            level: "info",
            metrics: false,
            audit: false
        },
        file: {
            level: "info",
            metrics: false,
            audit: false,
            handler: function(settings) {
                const fs   = require('fs');
                const path = require('path');

                const logPath = path.join('/data', 'nodered.log');
                const stream  = fs.createWriteStream(logPath, { flags: 'a' });

                const LEVEL_NAMES = {
                    10: 'FATAL',
                    20: 'ERROR',
                    30: 'WARN',
                    40: 'INFO',
                    50: 'DEBUG',
                    60: 'TRACE'
                };

                return function(msg) {
                    const ts    = new Date(msg.timestamp).toISOString();
                    const level = LEVEL_NAMES[msg.level] || String(msg.level);
                    stream.write(`[${ts}] [${level}] ${msg.msg}\n`);
                };
            }
        }
    },

    // =========================================================================
    // Personalización del editor
    // =========================================================================
    editorTheme: {
        page: {
            title: "RSA — Control Sísmico"
        },
        header: {
            title: "RSA Seismic Network",
            image: null
        }
    },

    // =========================================================================
    // Ajustes de rendimiento y reconexión
    // =========================================================================
    debugMaxLength: 1000,
    mqttReconnectTime: 15000,
    serialReconnectTime: 15000,

    // =========================================================================
    // Contexto de flujo: habilita almacenamiento en memoria (default)
    // =========================================================================
    contextStorage: {
        default: {
            module: "memory"
        }
    }
};
