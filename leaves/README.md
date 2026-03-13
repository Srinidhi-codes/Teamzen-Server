# Leaves Module

## Overview
The `leaves` app manages the lifecycle of leave requests, from application by employees to approval by managers or HR.

## File Breakdown

### `models.py`
- **`LeaveType`**: Defines categories like Casual Leave, Sick Leave, etc., along with their policies (e.g., carry-forward rules).
- **`LeaveRequest`**: Tracks individual applications, including dates, reason, status (Pending, Approved, Rejected), and attachments.
- **`LeaveBalance`**: Tracks available and used leaves for each employee per `LeaveType`.

### `services.py`
- **Purpose**: Contains complex business logic that doesn't belong in models or views.
- **Logic**: Calculating leave duration (excluding holidays/weekends), checking for balance availability, and processing approvals.

### `signals.py`
- **Purpose**: Hooks into model events.
- **Example**: Automatically creating `LeaveBalance` records for new users.

### `tasks.py`
- **Purpose**: Celery tasks for asynchronous processing.
- **Example**: Sending email notifications after a leave request is submitted or updated.

### `graphql/` (Directory)
- **`queries.py`**: Queries for viewing leave history and balances.
- **`mutations.py`**: Mutations for applying for leave and updating request status.

## Workflow
1. **Application**: Employee submits a `LeaveRequest`.
2. **Validation**: `services.py` checks for overlapping leaves and sufficient balance.
3. **Notification**: `tasks.py` sends an alert to the manager.
4. **Action**: Manager approves/rejects via GraphQL mutation, updating the `LeaveRequest` status and adjusting `LeaveBalance` if approved.
