"""
Gunicorn configuration for Sugna Enterprise Suite.

This file is loaded by Gunicorn using `-c`.
"""

from __future__ import annotations

import os


bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")

workers = int(os.environ.get("GUNICORN_WORKERS", "3"))
threads = int(os.environ.get("GUNICORN_THREADS", "2"))

# Threads work well for Django (especially for I/O bound workloads).
worker_class = os.environ.get("GUNICORN_WORKER_CLASS", "gthread")

timeout = int(os.environ.get("GUNICORN_TIMEOUT", "60"))
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.environ.get("GUNICORN_KEEPALIVE", "5"))

loglevel = os.environ.get("GUNICORN_LOG_LEVEL", os.environ.get("DJANGO_LOG_LEVEL", "info")).lower()
accesslog = "-"
errorlog = "-"

capture_output = True

# Gunicorn expects an integer for `max_requests`. Use 0 to disable.
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", "0"))
max_requests_jitter = int(os.environ.get("GUNICORN_MAX_REQUESTS_JITTER", "0"))

