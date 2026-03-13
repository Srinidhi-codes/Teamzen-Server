# Users Module

## Overview
The `users` app handles the identity and authentication layer of the system. It extends the default Django User model to include HR-specific fields and roles.

## File Breakdown

### `models.py`
- **`CustomUser`**: Inherits from `AbstractUser`. Includes fields for:
    - **Role**: `superadmin`, `admin`, `hr`, `manager`, `employee`.
    - **Employment**: `employee_id`, `department`, `designation`, `manager`, `office_location`.
    - **Personal**: `profile_picture`, `phone_number`, `date_of_birth`.
    - **Financial**: `bank_account_number`, `aadhar_number`, `pan_number`.

### `authentication.py`
- Contains custom authentication logic or token handlers (if JWT or custom schemes are used).

### `views.py`
- Legacy or specialized REST views for user management, profile updates, or authentication overrides.

### `serializers.py`
- Django Rest Framework (DRF) serializers for converting user data to/from JSON (mostly used for REST-based authentication or admin tools).

### `graphql/` (Directory)
- **`queries.py`**: Defintions for fetching user data via GraphQL (e.g., `me`, `userById`).
- **`mutations.py`**: Definitions for updating user profiles or authentication actions.

## Key Logic
- **Role-Based Access Control (RBAC)**: Roles are defined as choices on the user model, allowing for simple yet powerful permission checks across the system.
- **Organization Scoping**: Most users are tied to an `Organization`, ensuring data isolation in a multi-tenant-like structure.
