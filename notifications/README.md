# Notifications Module

## Overview
The `notifications` app provides a centralized service for sending real-time alerts and emails to users across the platform.

## File Breakdown

### `models.py`
- **`Notification`**: Stores in-app alerts with fields for `recipient`, `message`, `type` (Success, Warning, Info), and `is_read` status.

### `consumers.py`
- **Purpose**: Django Channels Consumer.
- **Logic**: Handles WebSocket connections for real-time delivery of notifications to the frontend.

### `tasks.py`
- **Logic**: High-priority Celery tasks for sending emails (via SMTP) and pushing updates to WebSocket groups.

### `email_backends.py`
- **Purpose**: Custom email backend configurations (e.g., for logging or specialized delivery services).

### `middleware.py`
- **Purpose**: Handles authentication for WebSocket connections, ensuring only the intended recipient receives their notifications.

### `utils.py`
- **Purpose**: Helper functions for formatting notification messages and determining delivery methods based on user preferences.

## Key Design Patterns
- **Fan-out Pattern**: A single event (like a leave approval) can trigger multiple notifications (Email + In-app).
- **Asynchronous Delivery**: All external communications (Email/Push) are offloaded to Celery to prevent blocking the main request-response cycle.
- **Real-time Updates**: Uses WebSockets to ensure users see alerts instantly without refreshing the page.
