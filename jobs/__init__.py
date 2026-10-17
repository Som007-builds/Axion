# jobs/__init__.py
"""
Durable background jobs for Axion.

The API never runs long work inline any more: ingestion cycles and research
queries are submitted to a queue and polled through `GET /api/jobs/{id}`.

Two backends, one contract (`jobs.backend.submit`):

  * **RQ + Redis** — used whenever `REDIS_URL` is configured. Work runs in a
    separate `axion-worker` process, survives API restarts, and job/progress
    state is shared across processes.
  * **Inline threads** — the fallback when `REDIS_URL` is unset (local dev,
    tests). Same job API, but jobs are lost if the process exits.
"""
