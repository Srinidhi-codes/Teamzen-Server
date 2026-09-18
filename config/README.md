# config

Django **project** package: settings, root URLs, ASGI/WSGI, Celery app.

**Learn:** [01 Django foundations](../../docs/backend/01-django-foundations.md) · [09 Celery](../../docs/backend/09-celery-queues.md) · [10 Channels](../../docs/backend/10-realtime-channels.md)

| File | Role |
|------|------|
| `settings.py` | Apps, middleware, JWT, CORS, Beat schedule |
| `urls.py` | `/graphql/`, `/api/…`, `/mcp/` |
| `asgi.py` | Daphne: HTTP + WebSockets |
| `celery.py` | Worker autodiscover |
