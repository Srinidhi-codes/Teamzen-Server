# GraphQL Utilities

## Overview
The `graphql_utils` directory contains shared types, decorators, and helper functions used by all GraphQL components in the project.

## File Breakdown

### `types.py`
- **Purpose**: Common Strawberry types (e.g., `ErrorType`, `SuccessType`, `PaginationInput`).
- **Benefit**: Ensures a consistent API response structure across the entire application.

### `decorators.py`
- **Purpose**: Custom Python decorators for GraphQL resolvers.
- **Examples**: `@login_required`, `@role_required(['admin', 'hr'])`.

### `converters.py`
- **Purpose**: Helpers to convert standard Django models or QuerySets into Strawberry-compatible types or lists.

## Benefits
- **DRY (Don't Repeat Yourself)**: Standardizes error handling and permission checks so they don't have to be rewritten in every app.
- **Consistency**: All mutations return a predictable response structure, making frontend integration much smoother.
