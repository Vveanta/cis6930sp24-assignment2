"""Celery application (worker: celery -A app.celery_app worker --loglevel=info)."""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

from celery import Celery

redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "norman_pd",
    broker=redis_url,
    backend=redis_url,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=720,
    task_soft_time_limit=660,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
)
