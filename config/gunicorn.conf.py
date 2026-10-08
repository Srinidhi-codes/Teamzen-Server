# ─────────────────────────────────────────────────────────────────────────────
# Gunicorn Configuration — Multi-worker ASGI with Uvicorn
# Optimized for local PC hosting (4+ cores typical)
# ─────────────────────────────────────────────────────────────────────────────

import multiprocessing
import os

# ── Workers ─────────────────────────────────────────────────────────────────
# Formula: (2 × CPU cores) + 1 for I/O-bound apps
# Cap at 4 to leave headroom for Redis, Postgres, Celery, Frontend
workers = min(int(os.getenv("GUNICORN_WORKERS", (2 * multiprocessing.cpu_count()) + 1)), 4)
worker_class = "uvicorn.workers.UvicornWorker"

# ── Binding ─────────────────────────────────────────────────────────────────
bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"

# ── Timeouts ────────────────────────────────────────────────────────────────
timeout = 120                # Kill worker if request takes >120s (PDF generation, AI calls)
graceful_timeout = 30        # Time to finish in-flight requests on shutdown
keepalive = 5                # Keep connections alive for 5s between requests

# ── Worker Lifecycle ────────────────────────────────────────────────────────
max_requests = 1000          # Restart worker after N requests (prevents memory leaks)
max_requests_jitter = 50     # Add randomness so workers don't all restart at once

# ── Pre-fork ────────────────────────────────────────────────────────────────
preload_app = True           # Load app before forking — saves ~50MB per worker

# ── Logging ─────────────────────────────────────────────────────────────────
accesslog = "-"              # stdout
errorlog = "-"               # stderr
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sμs'

# ── Server Mechanics ───────────────────────────────────────────────────────
# Forwarded headers from Nginx / Cloudflare
forwarded_allow_ips = "*"
proxy_protocol = False
