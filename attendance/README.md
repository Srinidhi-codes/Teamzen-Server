# Attendance Module

## Overview
The `attendance` app tracks employee presence, working hours, and location data during check-in/out.

## File Breakdown

### `models.py`
- **`Attendance`**: Stores daily logs including `check_in`, `check_out`, `working_hours`, and `status` (Present, Late, Absent).
- **`AttendanceCorrection`**: Allows employees to request changes to their logs (e.g., forgotten check-out).

### `services.py`
- **Logic**: Calculating work duration, identifying "Late" arrivals based on company policy, and validating geofencing or IP restrictions.

### `tasks.py`
- **Logic**: Daily background jobs to mark "Absent" for employees who didn't check in.

### `views.py`
- REST endpoints for bulk export of attendance data or specialized reports.

### `graphql/` (Directory)
- **`queries.py`**: Fetching personal or team attendance records.
- **`mutations.py`**: `checkIn` and `checkOut` actions.

## Key Logic
- **Real-time Status**: Tracking whether an employee is currently "on the clock".
- **Correction Workflow**: Similar to leaves, corrections require a reason and usually manager approval.
- **Automation**: Celery tasks ensure that attendance status is updated even if no action is taken by the user.
