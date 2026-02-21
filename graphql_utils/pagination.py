from typing import List, TypeVar, Generic, Optional
import strawberry
from django.db.models import QuerySet

T = TypeVar("T")

@strawberry.input
class SortInput:
    field: str = "created_at"
    direction: str = "desc"  # asc | desc

@strawberry.type
class PaginatedResponse(Generic[T]):
    results: List[T]
    total: int
    page: int
    page_size: int

def get_paginated_results(
    qs: QuerySet,
    page: int = 1,
    page_size: int = 10,
    sort: Optional[SortInput] = None,
    default_sort_field: str = "created_at"
) -> dict:
    """
    Reusable pagination and sorting logic for Strawberry GraphQL queries.
    
    Args:
        qs: The base Django QuerySet (already filtered).
        page: Current page number (1-based).
        page_size: Number of items per page.
        sort: Optional SortInput object.
        default_sort_field: Field to sort by if no sort input provided.
        
    Returns:
        dict containing results, total, page, and page_size.
    """
    
    # -------------------------
    # SORTING
    # -------------------------
    if sort:
        direction = "" if sort.direction == "asc" else "-"
        qs = qs.order_by(f"{direction}{sort.field}")
    else:
        # Check if default_sort_field needs descending order (often implies latest first)
        # Using a simple heuristic or just defaulting to descending for consistency with typical requirements
        qs = qs.order_by(f"-{default_sort_field}")

    # -------------------------
    # TOTAL COUNT
    # -------------------------
    total = qs.count()

    # -------------------------
    # PAGINATION BOUNDS
    # -------------------------
    if page < 1:
        page = 1

    if page_size < 1:
        page_size = 10

    start = (page - 1) * page_size
    end = start + page_size

    # -------------------------
    # SLICING
    # -------------------------
    results = list(qs[start:end])

    return {
        "results": results,
        "total": total,
        "page": page,
        "page_size": page_size
    }
