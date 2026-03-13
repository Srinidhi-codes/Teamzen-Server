# GraphQL API Layer

## Overview
The `graphql_api` directory serves as the orchestration layer for the entire platform's API. It aggregates queries and mutations from across all individual Django apps.

## File Breakdown

### `schema.py`
- **Purpose**: The root GraphQL schema definition.
- **Logic**: Combines sub-queries and sub-mutations from `users`, `attendance`, `leaves`, `organizations`, `notifications`, and `dashboard_queries` into a single, unified `Query` and `Mutation` type.

### `dashboard_queries.py`
- **Purpose**: Specialized queries for the dashboard UI.
- **Logic**: Aggregates data from multiple models (e.g., total employees, pending leaves, attendance stats for today) into efficient, single-request types to minimize frontend network overhead.

### `auth.py`
- **Purpose**: GraphQL-specific authentication helpers.
- **Logic**: Provides decorators or logic for checking user permissions and roles within GraphQL resolvers.

## Design Patterns
- **Schema Stitching (Internal)**: Using Strawberry's inheritance model to combine multiple query classes into one.
- **Aggregated Resolvers**: Reducing the "N+1" problem by providing specialized dashboard queries that fetch related data in fewer database hits.
