"""Long-running augmentation task (runs in Celery worker process)."""
from __future__ import annotations

import os
import tempfile

from dotenv import load_dotenv

load_dotenv()

from app.celery_app import celery_app
from app.job_store import (
    _key,
    get_redis,
    set_job_error_code,
    set_job_progress,
    store_job_results,
)

from app.utils.geocoding import GeocodingQuotaError


@celery_app.task(bind=True, name="augment.run_job")
def run_augment_job(self, job_id: str) -> dict:
    """
    Load SQLite snapshot from Redis, run augment_data, push CSV + updated DB back to Redis.
    """
    from app.utils.augment import augment_data

    r = get_redis()
    db_key = _key(job_id, "sqlite_in")
    db_bytes = r.get(db_key)
    if not db_bytes:
        raise ValueError(f"No SQLite payload in Redis for job {job_id}")

    def _progress(stage: str, percent: int, detail: str | None) -> None:
        set_job_progress(job_id, stage, percent, detail)

    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".db", prefix=f"normanpd_{job_id}_")
        os.close(fd)
        with open(tmp_path, "wb") as f:
            f.write(db_bytes)

        _progress("Starting", 2, None)
        try:
            csv_path = augment_data(tmp_path, progress_cb=_progress)
        except GeocodingQuotaError as e:
            set_job_error_code(job_id, "geocoding_quota", str(e))
            raise

        with open(csv_path, "rb") as f:
            csv_bytes = f.read()
        with open(tmp_path, "rb") as f:
            sqlite_out = f.read()

        store_job_results(job_id, sqlite_out, csv_bytes)
        r.delete(db_key)
        return {"ok": True, "job_id": job_id}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
