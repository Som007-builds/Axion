# jobs/worker.py
"""RQ worker entry point.

Run one or more workers alongside the API:

    python -m jobs.worker

Requires `REDIS_URL` to point at the same Redis the API uses. The worker needs
Neo4j, ChromaDB and the LLM keys — it is a full Axion runtime, not a thin
consumer — so in Docker it reuses the API image with a different command.
"""
from __future__ import annotations

import logging
import sys

import config


def _worker_class():
    """RQ's forking worker where available, `SimpleWorker` otherwise.

    RQ's default worker runs each job in a forked child so the parent can
    enforce `job_timeout`. Windows has no `os.fork`, so there the worker must
    use `SimpleWorker`, which executes jobs in-process (timeouts are then not
    enforced) — better than a worker that cannot start at all.
    """
    import os

    from rq import SimpleWorker, Worker

    if hasattr(os, "fork"):
        return Worker
    return SimpleWorker


def main() -> int:
    logging.basicConfig(
        level=getattr(logging, config.__dict__.get("LOG_LEVEL", "INFO"), logging.INFO),
        format="[%(asctime)s] %(levelname)s - %(name)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    if not config.REDIS_URL:
        logger.error(
            "REDIS_URL is not set — the worker has no queue to consume. "
            "Set REDIS_URL (e.g. redis://localhost:6379/0) and retry."
        )
        return 2

    try:
        from rq import Queue
    except ImportError:
        logger.error(
            "The 'rq' package is not installed. Install it with "
            "`pip install rq` (it is already in requirements.txt)."
        )
        return 2

    from jobs import redis_conn
    from jobs.backend import QUEUE_NAME

    client = redis_conn.get_redis()
    if client is None:
        logger.error("Could not connect to Redis at REDIS_URL — retrying is left to the supervisor.")
        return 3

    queue = Queue(QUEUE_NAME, connection=client)
    worker_class = _worker_class()
    if worker_class.__name__ == "SimpleWorker":
        logger.warning(
            "os.fork() is unavailable: running jobs in-process (SimpleWorker). "
            "Job timeouts are not enforced on this platform."
        )
    logger.info("Axion worker listening on queue '%s'", QUEUE_NAME)

    worker = worker_class([queue], connection=client)
    worker.work()
    return 0


if __name__ == "__main__":
    sys.exit(main())
