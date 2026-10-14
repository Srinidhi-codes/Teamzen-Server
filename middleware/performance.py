"""
Performance monitoring middleware for TeamZen Backend.

Logs slow requests, tracks request timing, and monitors database query counts.
Enable by adding 'middleware.performance.PerformanceMiddleware' to MIDDLEWARE.
"""

import logging
import time

from django.conf import settings
from django.db import connection, reset_queries

logger = logging.getLogger("teamzen.performance")


class PerformanceMiddleware:
    """
    Middleware that measures request processing time and logs slow requests.

    Features:
    - Logs total request time
    - Counts and logs SQL queries per request
    - Warns on slow requests (>1s) and N+1 query patterns (>10 queries)
    - Adds X-Request-Time header to responses
    """

    # Thresholds (can be overridden via settings)
    SLOW_REQUEST_THRESHOLD = getattr(settings, "SLOW_REQUEST_THRESHOLD", 1.0)  # seconds
    MAX_QUERIES_WARNING = getattr(settings, "MAX_QUERIES_WARNING", 10)

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Enable query logging in debug mode
        if settings.DEBUG:
            reset_queries()

        start_time = time.monotonic()

        response = self.get_response(request)

        duration = time.monotonic() - start_time

        # Add timing header (useful for frontend/Cloudflare debugging)
        response["X-Request-Time"] = f"{duration:.4f}s"

        # Log slow requests
        path = request.path
        method = request.method

        if duration > self.SLOW_REQUEST_THRESHOLD:
            logger.warning(
                "SLOW REQUEST: %s %s took %.3fs (threshold: %.1fs)",
                method,
                path,
                duration,
                self.SLOW_REQUEST_THRESHOLD,
            )

        # Log query count warnings (only when DEBUG is on)
        if settings.DEBUG:
            query_count = len(connection.queries)
            if query_count > self.MAX_QUERIES_WARNING:
                logger.warning(
                    "N+1 QUERY ALERT: %s %s executed %d queries (threshold: %d). "
                    "Consider using select_related/prefetch_related.",
                    method,
                    path,
                    query_count,
                    self.MAX_QUERIES_WARNING,
                )
            # Log all request timings in debug
            if duration > 0.5:
                logger.info(
                    "%s %s — %.3fs, %d queries",
                    method,
                    path,
                    duration,
                    query_count,
                )

        return response
