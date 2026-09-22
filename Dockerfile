FROM python:3.11-slim

WORKDIR /usr/src/app
ENV PYTHONUNBUFFERED=1 TZ=Europe/Rome

# Dipendenze prima del codice: layer di cache più efficace
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p data/logs

# Il comando lo decide docker-compose (bot oppure web)
CMD ["python", "main.py"]
