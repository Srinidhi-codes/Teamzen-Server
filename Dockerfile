FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN apt-get update && apt-get install -y supervisor && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

COPY . . 
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Static files will be collected at runtime to avoid build-time environment issues

EXPOSE 8000

# Start Supervisor to run Daphne, Celery, and Celery Beat concurrently
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]