FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . . 

# Static files will be collected at runtime to avoid build-time environment issues

EXPOSE 8000

# Render injects $PORT. Daphne (ASGI) must bind to 0.0.0.0:$PORT so Render
# can detect the open port. Shell form is needed to expand the $PORT variable.
CMD daphne -b 0.0.0.0 -p ${PORT:-8000} config.asgi:application