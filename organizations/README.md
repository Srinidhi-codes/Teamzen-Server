# Organizations Module

## Overview
The `organizations` app defines the structural hierarchy of the companies using the payroll system. It manages the entities that users belong to.

## File Breakdown

### `models.py`
- **`Organization`**: The top-level entity representing a company.
- **`Department`**: Linked to an organization (e.g., Engineering, HR).
- **`Designation`**: Roles within a department (e.g., Senior Developer, Manager).
- **`OfficeLocation`**: Physical or remote locations for the organization.

### `admin.py`
- Customizes the Django Admin interface to manage organizations, departments, and designations with specific search and filter options.

### `views.py`
- Provides REST endpoints for organizational data if needed.

### `graphql/` (Directory)
- **`queries.py`**: GraphQL types and queries for fetching organization structure.
- **`mutations.py`**: Logic for creating or updating departments and designations.

## Key Logic
- **Hierarchical Structure**: Designation and Departments are related back to the Organization, providing a clear tree structure for reporting.
- **Multi-tenancy Basis**: The `Organization` model is the primary key for scoping data in other apps like `leaves` and `payroll`.
