# Payroll System Backend

Django + Strawberry GraphQL + DRF + Celery. Ports: API **8000**, MCP facade **8001**.

**Learn the architecture (fresher path):** [`docs/backend/README.md`](../docs/backend/README.md)

Short survey: [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md)

## Getting started

Prerequisites: Python 3.10+, Redis, PostgreSQL (recommended), optional RabbitMQ.

1. `pip install -r requirements.txt`
2. Copy env from `.env.example` (never commit secrets).
3. `python manage.py migrate`
4. `python manage.py runserver` or Daphne on `:8000`
5. `celery -A config worker -l info` and Beat for scheduled jobs
6. MCP: `python mcp_servers/teamzen_server.py`

Root files: `manage.py`, `Dockerfile`, `requirements.txt`, `render.yaml`, `supervisord.conf`. Compose lives in the **repo root**.
