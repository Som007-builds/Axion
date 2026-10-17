# jobs/backend.py
"""Job submission: RQ when Redis is available, inline threads otherwise.

Both paths hand off to `jobs.tasks.run_job`, so the job API seen by clients is
identical either way — only durability and cross-process visibility differ.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

import config
from jobs import redis_conn
from jobs.store import (
    STATUS_QUEUED,
    STATUS_RUNNING,
    get_job_store,
    new_job_id,
)
from jobs.tasks import (
    JOB_CUSTOM_INGESTION,
    JOB_INGESTION,
    JOB_QUERY,
    run_job,
)

logger = logging.getLogger(__name__)

QUEUE_NAME = "axion"
RUN_JOB_PATH = "jobs.tasks.run_job"

INGESTION_KINDS = (JOB_INGESTION, JOB_CUSTOM_INGESTION)
ACTIVE_STATUSES = (STATUS_QUEUED, STATUS_RUNNING)

# Only a couple of inline workers: jobs are LLM/IO-bound and heavy, and
# ingestion must not run concurrently with itself.
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="axion-job")


class JobConflictError(RuntimeError):
    """Raised when the same kind of job is already queued or running."""


def backend_name() -> str:
    """`"rq"` when a worker will pick the job up, else `"inline"`."""
    return "rq" if redis_conn.get_redis() is not None else "inline"


def active_ingestion_job() -> dict | None:
    """The queued/running ingestion job, if any. Shared across processes."""
    store = get_job_store()
    for record in store.list_recent(25):
        if record.get("kind") in INGESTION_KINDS and record.get("status") in ACTIVE_STATUSES:
            return record
    return None


def submit(kind: str, payload: dict | None = None) -> tuple[str, str]:
    """Enqueue one job. Returns ``(job_id, backend)``.

    Raises `JobConflictError` if an ingestion job is already in flight —
    concurrent ingestion cycles would double-write the graph.
    """
    payload = payload or {}
    store = get_job_store()

    if kind in INGESTION_KINDS and active_ingestion_job() is not None:
        raise JobConflictError("An ingestion pipeline is already running")

    job_id = new_job_id()
    store.create(job_id, kind=kind, payload=payload)

    client = redis_conn.get_redis()
    if client is not None:
        try:
            from rq import Queue

            queue = Queue(QUEUE_NAME, connection=client)
            queue.enqueue(
                RUN_JOB_PATH,
                kind,
                job_id,
                payload,
                job_id=job_id,
                job_timeout=config.JOB_TIMEOUT_SECONDS,
                result_ttl=config.JOB_TTL_SECONDS,
                failure_ttl=config.JOB_TTL_SECONDS,
            )
            logger.info("Job %s (%s) queued on Redis", job_id, kind)
            return job_id, "rq"
        except Exception as exc:  # noqa: BLE001 - fall back rather than fail
            logger.warning(
                "Job %s (%s): could not enqueue on Redis (%s) — running inline "
                "instead; the job will not survive a restart.",
                job_id, kind, exc,
            )

    _executor.submit(_run_inline, kind, job_id, payload)
    logger.info("Job %s (%s) started inline", job_id, kind)
    return job_id, "inline"


def _run_inline(kind: str, job_id: str, payload: dict) -> None:
    try:
        run_job(kind, job_id, payload)
    except Exception:  # noqa: BLE001 - already recorded by run_job
        pass


__all__ = [
    "JobConflictError",
    "JOB_INGESTION",
    "JOB_CUSTOM_INGESTION",
    "JOB_QUERY",
    "active_ingestion_job",
    "backend_name",
    "submit",
]
