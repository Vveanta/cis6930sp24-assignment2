"""Redis helpers for passing SQLite / CSV between web and Celery worker (separate containers)."""
from __future__ import annotations

import json
import os
from typing import Any, Optional

import redis

_CLIENT: Optional[redis.Redis] = None

KEY_PREFIX = "normanpd:job"
TTL_SECONDS = 86400  # 24 hours


def get_redis() -> redis.Redis:
    global _CLIENT
    if _CLIENT is None:
        url = os.environ.get("REDIS_URL")
        if not url:
            raise RuntimeError("REDIS_URL is not set")
        _CLIENT = redis.from_url(url, decode_responses=False)
    return _CLIENT


def _key(job_id: str, suffix: str) -> str:
    return f"{KEY_PREFIX}:{job_id}:{suffix}"


def store_job_payload(
    job_id: str,
    sqlite_bytes: bytes,
    failed_urls: list[str],
    skipped_urls: list[str],
) -> None:
    r = get_redis()
    meta = json.dumps({"failed_urls": failed_urls, "skipped_urls": skipped_urls})
    pipe = r.pipeline()
    pipe.setex(_key(job_id, "sqlite_in"), TTL_SECONDS, sqlite_bytes)
    pipe.setex(_key(job_id, "meta"), TTL_SECONDS, meta.encode("utf-8"))
    pipe.execute()


def store_job_results(job_id: str, sqlite_out: bytes, csv_bytes: bytes) -> None:
    r = get_redis()
    pipe = r.pipeline()
    pipe.setex(_key(job_id, "sqlite_out"), TTL_SECONDS, sqlite_out)
    pipe.setex(_key(job_id, "csv"), TTL_SECONDS, csv_bytes)
    pipe.execute()


def get_job_meta(job_id: str) -> dict[str, Any]:
    r = get_redis()
    raw = r.get(_key(job_id, "meta"))
    if not raw:
        return {"failed_urls": [], "skipped_urls": []}
    return json.loads(raw.decode("utf-8"))


def pop_job_results_for_finalize(job_id: str) -> tuple[bytes, bytes]:
    """Read and delete result blobs after a successful Celery task."""
    r = get_redis()
    sk_sql = _key(job_id, "sqlite_out")
    sk_csv = _key(job_id, "csv")
    db_b = r.get(sk_sql)
    csv_b = r.get(sk_csv)
    if not db_b or not csv_b:
        raise ValueError("Missing job results in Redis")
    r.delete(sk_sql, sk_csv, _key(job_id, "meta"))
    return db_b, csv_b


def clear_job_keys(job_id: str) -> None:
    r = get_redis()
    r.delete(
        _key(job_id, "sqlite_in"),
        _key(job_id, "sqlite_out"),
        _key(job_id, "csv"),
        _key(job_id, "meta"),
    )
