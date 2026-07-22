FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fuente y configuración
COPY config.json .
COPY regional_event_correlator.py .

# Ejecución en modo unbuffered para salida inmediata de logs
CMD ["python", "-u", "regional_event_correlator.py"]
