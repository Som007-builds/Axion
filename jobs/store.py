# jobs/store.py
"""Job registry: durable (Redis) with an in-memory fallback.

A "job" is a small record describing one unit of background work:

    {id, kind, status, created_at, started_at, finished_at, result, error}

`status` is one of `queued`, `running`, `completed`, `failed`.

When Redis is configured the record lives under `axion:job:<id>` with a TTL, so
the API process and the worker process share it. Without Redis an in-memory
dict is used, which is enough for local development and tests but is not shared
across processes and does not survive a restart.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from typing import Any, Optional

import config
from jobs import redis_conn

logger = logging.getLogger(__name__)

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

TERMINAL_STATUSES = (STATUS_COMPLETED, STATUS_FAILED)

_JOB_KEY = "axion:job:{}"
_INDEX_KEY = "axion:jobs:index"

# Fields that must never be echoed to an API client.
_PRIVATE_FIELDS = ("_payload",)


def new_job_id() -> str:
    return uuid.uuid4().hex


def public_view(record: dict) -> dict:
    """Strip internal fields from a job record before returning it."""
    return {k: v for k, v in record.items() if k not in _PRIVATE_FIELDS}


class MemoryJobStore:
    """Process-local job registry (fallback backend)."""

    def __init__(self, max_jobs: int = 200):
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._max_jobs = max_jobs

    def create(self, job_id: str, kind: str, payload: dict | None = None) -> dict:
        record = {
            "id": job_id,
            "kind": kind,
            "status": STATUS_QUEUED,
            "created_at": time.time(),
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
            "backend": "inline",
            "_payload": payload or {},
        }
        with self._lock:
            self._jobs[job_id] = record
            while len(self._jobs) > self._max_jobs:
                oldest = min(self._jobs, key=lambda k: self._jobs[k]["created_at"])
                self._jobs.pop(oldest, None)
        return record

    def update(self, job_id: str, **fields) -> Optional[dict]:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return None
            record.update(fields)
            return dict(record)

    def get(self, job_id: str) -> Optional[dict]:
        with self._lock:
            record = self._jobs.get(job_id)
            return dict(record) if record else None

    def list_recent(self, limit: int = 20) -> list[dict]:
        with self._lock:
            records = sorted(
                self._jobs.values(), key=lambda r: r["created_at"], reverse=True
            )
            return [dict(r) for r in records[:limit]]

    def clear(self) -> None:
        with self._lock:
            self._jobs.clear()


class RedisJobStore:
    """Cross-process job registry backed by Redis."""

    def __init__(self, client, ttl: int):
        self._redis = client
        self._ttl = ttl

    def create(self, job_id: str, kind: str, payload: dict | None = None) -> dict:
        record = {
            "id": job_id,
            "kind": kind,
            "status": STATUS_QUEUED,
            "created_at": time.time(),
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
            "backend": "rq",
            "_payload": payload or {},
        }
        self._write(record)
        try:
            self._redis.zadd(_INDEX_KEY, {job_id: record["created_at"]})
            self._redis.expire(_INDEX_KEY, self._ttl)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Job store: could not index job %s: %s", job_id, exc)
        return record

    def update(self, job_id: str, **fields) -> Optional[dict]:
        record = self.get(job_id)
        if record is None:
            return None
        record.update(fields)
        self._write(record)
        return record

    def get(self, job_id: str) -> Optional[dict]:
        try:
            raw = self._redis.get(_JOB_KEY.format(job_id))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Job store: read failed for %s: %s", job_id, exc)
            return None
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Job store: corrupt record for %s", job_id)
            return None

    def list_recent(self, limit: int = 20) -> list[dict]:
        try:
            ids = self._redis.zrevrange(_INDEX_KEY, 0, max(limit - 1, 0))
        except Exception:  # noqa: BLE001
            return []
        out = []
        for job_id in ids:
            # The shared client is in bytes mode (RQ needs it), so ids come
            # back as bytes and must be decoded before building a key.
            key_id = job_id.decode() if isinstance(job_id, bytes) else job_id
            record = self.get(key_id)
            if record:
                out.append(record)
        return out

    def clear(self) -> None:
        return None

    def _write(self, record: dict) -> None:
        job_id = record["id"]
        try:
            self._redis.set(
                _JOB_KEY.format(job_id),
                json.dumps(record, default=str),
                ex=self._ttl,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Job store: write failed for %s: %s", job_id, exc)


_memory = MemoryJobStore()
_redis_store: Optional[RedisJobStore] = None
_lock = threading.Lock()


def get_job_store():
    """Return the Redis-backed store when Redis is reachable, else memory."""
    global _redis_store
    client = redis_conn.get_redis()
    if client is None:
        return _memory
    with _lock:
        if _redis_store is None:
            _redis_store = RedisJobStore(client, ttl=config.JOB_TTL_SECONDS)
        return _redis_store


def reset_caches() -> None:
    """Test helper: forget cached clients/stores."""
    global _redis_store
    with _lock:
        _redis_store = None
    redis_conn.reset()
    _memory.clear()
