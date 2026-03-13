# Config Module

## Overview
The `config` directory is the core of the Django project. It contains project-wide settings, routing configurations, and integration points for ASGI, WSGI, and Celery.

## File Breakdown

### `settings.py`
- **Purpose**: Main configuration file for the Django project.
- **Key Sections**:
    - `INSTALLED_APPS`: Lists all local apps (`users`, `organizations`, etc.) and third-party packages.
    - `MIDDLEWARE`: Security, session, and authentication hooks.
    - `DATABASES`: Database connection settings (typically sourced from environment variables).
    - `AUTH_USER_MODEL`: Set to `users.CustomUser` for extended user functionality.
    - `STRAWBERRY_DJANGO`: Configuration for GraphQL integration.
    - `CELERY_BROKER_URL`: Connection string for Redis/RabbitMQ.

### `urls.py`
- **Purpose**: Root URL configuration.
- **Key Routes**:
    - `/admin/`: Django Admin interface.
    - `/graphql/`: Entry point for all GraphQL API requests.
    - Authentication routes (if any REST endpoints exist).

### `celery.py`
- **Purpose**: Initializes the Celery application.
- **Logic**: Automatically discovers tasks in all registered Django apps (e.g., `leaves/tasks.py`, `notifications/tasks.py`).

### `asgi.py` & `wsgi.py`
- **Purpose**: Entry points for the web server.
- **ASGI**: Used for asynchronous protocols (WebSockets/Django Channels).
- **WSGI**: Used for standard synchronous HTTP requests.

### `__init__.py`
- Ensures that Celery app is loaded when Django starts.

## Design Patterns
- **Environment-Based Config**: Uses `.env` files to keep secrets and environment-specific settings out of the codebase.
- **Modular URLS**: Keeps the root `urls.py` clean by including app-specific URLs where necessary.
