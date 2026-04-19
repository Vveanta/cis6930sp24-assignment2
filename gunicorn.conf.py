"""Gunicorn settings for production (e.g. Render). Import path: gunicorn run:app -c gunicorn.conf.py"""
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
# Upload + PDF + geocoding + augmentation can exceed Gunicorn's default 30s timeout.
timeout = 300
graceful_timeout = 60
# Free/small instances: one worker avoids duplicate RAM for the heavy pandas/PDF stack.
workers = 1
threads = 1
worker_class = "sync"
# Recycle workers after heavy requests to mitigate memory growth (OOM on small RAM).
max_requests = 50
max_requests_jitter = 10
