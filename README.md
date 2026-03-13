# Payroll System Backend

## Overview
This is the backend for the Payroll System, built using **Django**, **Strawberry GraphQL**, and **Celery**. It handles user management, organization structures, leave management, attendance tracking, payroll processing, and notifications.

## Architecture
- **Web Framework**: [Django](https://www.djangoproject.com/)
- **API Engine**: [Strawberry GraphQL](https://strawberry.rocks/) (Pythonic GraphQL)
- **Task Queue**: [Celery](https://docs.celeryq.dev/) with Redis/RabbitMQ
- **Database**: PostgreSQL (recommended)
- **Real-time**: Django Channels (for notifications/websockets)

## Directory Structure

### Core Apps
- `config/`: Project-wide settings, URL configuration, and ASGI/WSGI entry points.
- `users/`: Custom user model, authentication, and user-related GraphQL queries/mutations.
- `organizations/`: Management of organizations, departments, designations, and office locations.
- `leaves/`: Leave types, leave applications, and approval workflows.
- `attendance/`: Check-in/out logic, location tracking, and attendance corrections.
- `payroll/`: Salary structure, payrun processing, and payslip generation.
- `notifications/`: Centralized notification system (Email, Web Push, In-app) using background tasks.

### API & Utilities
- `graphql_api/`: The root GraphQL schema and combined query/mutation entry points.
- `graphql_utils/`: Shared utilities, decorators, and basic types for GraphQL.
- `ai_engine/`: (If present) AI-powered features like leave conflict detection or payroll analysis.

### Infrastructure
- `templates/`: HTML templates (mostly for emails).
- `staticfiles/`: Collected static assets.
- `temp_email/`: Temporary storage for email-related assets or logs.

## Getting Started

### Prerequisites
- Python 3.10+
- Pipenv or virtualenv
- Redis (for Celery and Channels)

### Installation
1. Install dependencies: `pip install -r requirements.txt`
2. Configure `.env` file (see `.env.example`).
3. Run migrations: `python manage.py migrate`
4. Start development server: `python manage.py runserver`
5. Start Celery worker: `celery -A config worker -l info`

## Root Files Breakdown

- `manage.py`: Django's command-line utility for administrative tasks (migrations, startserver, etc.).
- `Dockerfile`: Multi-stage build for containerizing the Django application.
- `docker-compose.yml`: (In project root) Orchestrates the backend, database, Redis, and worker services.
- `requirements.txt`: Lists all Python dependencies and their versions.
- `render.yaml`: Configuration for deploying the stack on Render.com.
- `supervisord.conf`: Manages multiple processes (Daphne, Celery) within a single container for easier management on Render's free tier.
- `.env`: Environment variables (Template: `.env.example`).
- `.dockerignore` & `.gitignore`: Ensures unnecessary files aren't tracked or containerized.


