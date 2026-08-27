FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar scripts Python
COPY mqtt_notify.py .

# Ejecución en modo unbuffered para salida inmediata de logs
ENTRYPOINT ["python", "-u"]
CMD ["mqtt_notify.py", "--help"]
