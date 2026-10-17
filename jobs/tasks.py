# jobs/tasks.py
"""The actual units of background work.

`run_job` is the single entry point the queue calls (both backends use it, and
RQ needs it importable by dotted path). It owns the job lifecycle: mark
running, execute, record the result or the failure.
"""
from __future__ import annotations

import json
import logging
import time

from jobs.store import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_RUNNING,
    get_job_store,
)

logger = logging.getLogger(__name__)

JOB_QUERY = "query"
JOB_INGESTION = "ingestion"
JOB_CUSTOM_INGESTION = "custom_ingestion"

_CONFIDENCE_MAP = {"high": 0.9, "medium": 0.6, "low": 0.3}


# ─── Query job ────────────────────────────────────────────────────────────────

def format_query_output(output: dict) -> dict:
    """Shape a coordinator result into the payload the frontend consumes.

    Extracted verbatim from the old synchronous `/api/query` handler so the job
    produces exactly the same response the client used to receive inline.
    """
    raw_result = output.get("raw", {}) or {}

    conf_str = str(raw_result.get("confidence_in_answer", "medium")).strip().lower()
    confidence_num = _CONFIDENCE_MAP.get(conf_str, 0.6)

    sources: set[str] = set()
    for item in raw_result.get("consensus", []) or []:
        if not isinstance(item, dict):
            continue
        for cit in item.get("citations", []) or []:
            if cit:
                sources.add(str(cit))
    for item in raw_result.get("disputed", []) or []:
        if not isinstance(item, dict):
            continue
        for key in ("position_a", "position_b"):
            position = item.get(key, {})
            if isinstance(position, dict) and position.get("paper"):
                sources.add(str(position["paper"]))

    sub_queries = (output.get("plan", {}) or {}).get("sub_queries", []) or []

    reflection_log = []
    for step in output.get("reflection_log", []) or []:
        if not isinstance(step, dict):
            continue
        reflection_log.append({
            "step": step.get("iteration", 1),
            "action": f"Iteration {step.get('iteration', 1)} reflection",
            "observation": step.get("assessment", ""),
            "reasoning": (
                f"Query refined: {step.get('refined_query')}"
                if step.get("refined_query")
                else "Context marked sufficient"
            ),
        })

    return {
        "report": output.get("report", ""),
        "raw": json.dumps(raw_result),
        "iterations": output.get("iterations", 1),
        "plan": sub_queries,
        "reflection_log": reflection_log,
        "confidence": confidence_num,
        "sources": sorted(sources),
    }


def job_query(payload: dict, job_id: str) -> dict:
    from agents.coordinator_v2 import run

    output = run(payload["question"], verbose=False)
    return format_query_output(output)


# ─── Ingestion jobs ───────────────────────────────────────────────────────────

def job_ingestion(payload: dict, job_id: str) -> dict:
    """One scheduled-style ingestion cycle across the configured topics."""
    from ingestion.scheduler import _run_ingestion_cycle

    return _run_ingestion_cycle()


def job_custom_ingestion(payload: dict, job_id: str) -> dict:
    """User-triggered ingestion for a topic, with progress tracking."""
    from ingestion.scheduler import run_custom_ingestion

    run_custom_ingestion(payload["topic"], payload["limit"])

    # run_custom_ingestion drives the progress tracker; read the final tally
    # back out so the job result carries real numbers.
    from ingestion.progress import progress_tracker

    snapshot = progress_tracker.get_progress()
    return {
        "mode": "custom",
        "topic": payload["topic"],
        "papers_added": snapshot.get("papers_added", 0),
        "claims_added": snapshot.get("claims_added", 0),
        "contradictions_found": snapshot.get("contradictions_found", 0),
    }


TASKS = {
    JOB_QUERY: job_query,
    JOB_INGESTION: job_ingestion,
    JOB_CUSTOM_INGESTION: job_custom_ingestion,
}


# ─── Lifecycle wrapper ────────────────────────────────────────────────────────

def run_job(kind: str, job_id: str, payload: dict | None = None) -> dict:
    """Execute one job, recording status transitions in the job store.

    Errors are recorded and re-raised so the queue backend can also see the
    failure (RQ marks the job failed; the inline backend just logs it).
    """
    store = get_job_store()
    payload = payload or {}
    store.update(job_id, status=STATUS_RUNNING, started_at=time.time())

    task = TASKS.get(kind)
    if task is None:
        message = f"unknown job kind: {kind}"
        store.update(job_id, status=STATUS_FAILED, error=message, finished_at=time.time())
        raise ValueError(message)

    try:
        result = task(payload, job_id)
    except Exception as exc:  # noqa: BLE001 - recorded, then re-raised
        logger.exception("Job %s (%s) failed", job_id, kind)
        store.update(
            job_id,
            status=STATUS_FAILED,
            # Deliberately generic: internal error text is not exposed to
            # clients (see the API's error-handling policy). Full detail is
            # in the server logs.
            error="Job failed. Check the server logs for details.",
            finished_at=time.time(),
        )
        raise

    store.update(
        job_id,
        status=STATUS_COMPLETED,
        result=result,
        finished_at=time.time(),
    )
    return result
