"""
Background job queue tests (offline).

Covers the job registry, the submit/lifecycle wrapper, the extracted query
formatter, and the cross-process progress mirror. Everything runs against the
in-memory fallback backend — no Redis server required.
"""
import json
import time
from unittest.mock import patch

import pytest

from jobs.store import (
    MemoryJobStore,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    public_view,
)


class FakeRedis:
    """Minimal stand-in for the handful of Redis calls the job code makes.

    Mirrors the real client's *bytes* mode (`decode_responses=False`): values and
    list entries come back as bytes, which is what RQ requires.
    """

    def __init__(self):
        self.data: dict[str, str] = {}
        self.zsets: dict[str, dict[str, float]] = {}

    def set(self, key, value, ex=None):
        self.data[key] = value

    def get(self, key):
        return self.data.get(key)

    def zadd(self, key, mapping):
        self.zsets.setdefault(key, {}).update(mapping)

    def zrevrange(self, key, start, end):
        items = sorted(
            self.zsets.get(key, {}).items(), key=lambda kv: kv[1], reverse=True
        )
        stop = None if end == -1 else end + 1
        return [k.encode() for k, _ in items[start:stop]]

    def expire(self, key, ttl):
        return True

    def ping(self):
        return True


@pytest.fixture
def memory_store(monkeypatch):
    """A fresh in-memory job registry wired into every consumer module."""
    store = MemoryJobStore()
    monkeypatch.setattr("jobs.store.get_job_store", lambda: store)
    monkeypatch.setattr("jobs.backend.get_job_store", lambda: store)
    monkeypatch.setattr("jobs.tasks.get_job_store", lambda: store)
    monkeypatch.setattr("jobs.redis_conn.get_redis", lambda: None)
    monkeypatch.setattr("jobs.redis_conn.is_configured", lambda: False)
    return store


def wait_for_status(store, job_id, statuses, timeout=10.0):
    """Poll the registry until the job reaches one of `statuses`."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        record = store.get(job_id)
        if record and record["status"] in statuses:
            return record
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} never reached {statuses}")


# ─── Registry ─────────────────────────────────────────────────────────────────

class TestJobStore:
    def test_create_returns_queued_record(self):
        store = MemoryJobStore()
        record = store.create("job-1", "query", {"question": "q"})
        assert record["status"] == STATUS_QUEUED
        assert record["started_at"] is None
        assert record["result"] is None

    def test_update_merges_fields(self):
        store = MemoryJobStore()
        store.create("job-1", "query")
        updated = store.update("job-1", status=STATUS_RUNNING, started_at=1.0)
        assert updated["status"] == STATUS_RUNNING
        assert store.get("job-1")["started_at"] == 1.0

    def test_update_unknown_job_returns_none(self):
        assert MemoryJobStore().update("missing", status=STATUS_FAILED) is None

    def test_list_recent_is_newest_first(self):
        store = MemoryJobStore()
        store.create("old", "query")
        time.sleep(0.01)
        store.create("new", "query")
        assert [r["id"] for r in store.list_recent()] == ["new", "old"]

    def test_memory_store_is_bounded(self):
        store = MemoryJobStore(max_jobs=3)
        for i in range(6):
            store.create(f"job-{i}", "query")
        assert len(store.list_recent(limit=10)) == 3

    def test_public_view_hides_internal_payload(self):
        store = MemoryJobStore()
        record = store.create("job-1", "query", {"question": "secret"})
        assert "_payload" not in public_view(record)
        assert public_view(record)["id"] == "job-1"


# ─── submit() / lifecycle ─────────────────────────────────────────────────────

class TestSubmit:
    def test_submit_runs_inline_without_redis(self, memory_store):
        from jobs import backend, tasks

        tasks.TASKS["test_echo"] = lambda payload, job_id: {"echo": payload["v"]}
        try:
            job_id, backend_name = backend.submit("test_echo", {"v": 7})
            assert backend_name == "inline"
            record = wait_for_status(memory_store, job_id, {STATUS_COMPLETED})
        finally:
            tasks.TASKS.pop("test_echo", None)

        assert record["result"] == {"echo": 7}
        assert record["started_at"] and record["finished_at"]

    def test_failed_job_records_a_generic_error(self, memory_store):
        from jobs import backend, tasks

        def boom(payload, job_id):
            raise RuntimeError("provider key sk-secret leaked")

        tasks.TASKS["test_boom"] = boom
        try:
            job_id, _ = backend.submit("test_boom")
            record = wait_for_status(memory_store, job_id, {STATUS_FAILED})
        finally:
            tasks.TASKS.pop("test_boom", None)

        assert record["result"] is None
        # Internal detail must not be exposed through the API payload.
        assert "sk-secret" not in (record["error"] or "")

    def test_submit_uses_rq_when_redis_is_available(self, memory_store, monkeypatch):
        from jobs import backend

        class FakeQueue:
            def __init__(self, *args, **kwargs):
                self.calls = []

            def enqueue(self, path, *args, **kwargs):
                # RQ passes the job function's own arguments positionally and
                # job_id/job_timeout/... as keywords.
                self.calls.append((path, args, kwargs))

        monkeypatch.setattr("jobs.redis_conn.get_redis", lambda: FakeRedis())
        monkeypatch.setattr("rq.Queue", FakeQueue)

        job_id, backend_name = backend.submit("query", {"question": "q"})

        assert backend_name == "rq"
        assert memory_store.get(job_id)["status"] == STATUS_QUEUED

    def test_rq_enqueue_failure_falls_back_to_inline(self, memory_store, monkeypatch):
        from jobs import backend, tasks

        monkeypatch.setattr("jobs.redis_conn.get_redis", lambda: FakeRedis())

        def broken_queue(*args, **kwargs):
            raise ConnectionError("redis went away")

        monkeypatch.setattr("rq.Queue", broken_queue)
        tasks.TASKS["test_echo"] = lambda payload, job_id: {"ok": True}
        try:
            job_id, backend_name = backend.submit("test_echo", {})
            assert backend_name == "inline"
            wait_for_status(memory_store, job_id, {STATUS_COMPLETED})
        finally:
            tasks.TASKS.pop("test_echo", None)

    def test_concurrent_ingestion_is_rejected(self, memory_store):
        from jobs import backend

        assert backend.active_ingestion_job() is None

        # Park an ingestion job in the queued state by hand (submitting a real
        # one would start the pipeline).
        memory_store.create("ing-1", backend.JOB_INGESTION)
        assert backend.active_ingestion_job()["id"] == "ing-1"

        with pytest.raises(backend.JobConflictError):
            backend.submit(backend.JOB_CUSTOM_INGESTION, {"topic": "t", "limit": 1})

    def test_ingestion_visible_across_processes(self, memory_store):
        """A queued ingestion must be discoverable from any process."""
        from jobs import backend

        memory_store.create("ing-1", backend.JOB_CUSTOM_INGESTION)
        assert backend.active_ingestion_job()["id"] == "ing-1"
        memory_store.update("ing-1", status=STATUS_COMPLETED)
        assert backend.active_ingestion_job() is None

    def test_unknown_job_kind_fails_cleanly(self, memory_store):
        from jobs.tasks import run_job

        memory_store.create("job-1", "nonsense")
        with pytest.raises(ValueError):
            run_job("nonsense", "job-1", {})
        assert memory_store.get("job-1")["status"] == STATUS_FAILED


# ─── Query job ────────────────────────────────────────────────────────────────

class TestQueryJob:
    def test_format_query_output_shape(self):
        from jobs.tasks import format_query_output

        output = {
            "report": "the report",
            "iterations": 2,
            "plan": {"sub_queries": ["a", "b"]},
            "reflection_log": [
                {"iteration": 1, "assessment": "thin", "refined_query": "better query"},
                {"iteration": 2, "assessment": "sufficient", "refined_query": None},
            ],
            "raw": {
                "confidence_in_answer": "high",
                "consensus": [{"citations": ["2301.00001", "2302.00002"]}],
                "disputed": [
                    {"position_a": {"paper": "2303.00003"}, "position_b": {"paper": None}}
                ],
            },
        }
        formatted = format_query_output(output)

        assert formatted["report"] == "the report"
        assert formatted["iterations"] == 2
        assert formatted["plan"] == ["a", "b"]
        assert formatted["confidence"] == pytest.approx(0.9)
        assert formatted["sources"] == ["2301.00001", "2302.00002", "2303.00003"]
        assert len(formatted["reflection_log"]) == 2
        assert json.loads(formatted["raw"])["confidence_in_answer"] == "high"

    def test_format_query_output_tolerates_missing_fields(self):
        from jobs.tasks import format_query_output

        formatted = format_query_output({})
        assert formatted["report"] == ""
        assert formatted["sources"] == []
        assert formatted["confidence"] == pytest.approx(0.6)

    def test_format_query_output_handles_non_dict_entries(self):
        """Malformed LLM output must not crash the job."""
        from jobs.tasks import format_query_output

        formatted = format_query_output({
            "raw": {"consensus": ["oops"], "disputed": ["nope"]},
        })
        assert formatted["sources"] == []

    def test_job_query_runs_the_coordinator(self):
        from jobs.tasks import job_query

        with patch("agents.coordinator_v2.run",
                   return_value={"report": "r", "raw": {}, "iterations": 1,
                                 "plan": {}, "reflection_log": []}) as run:
            result = job_query({"question": "what is up"}, "job-1")

        run.assert_called_once_with("what is up", verbose=False)
        assert result["report"] == "r"
        assert result["iterations"] == 1


# ─── Ingestion job ────────────────────────────────────────────────────────────

class TestIngestionJob:
    def test_custom_ingestion_job_reports_counts(self):
        from ingestion.progress import progress_tracker
        from jobs.tasks import job_custom_ingestion

        def fake_run(topic, limit):
            progress_tracker.start(topic, limit)
            progress_tracker.finish_paper(1.0, 4)
            progress_tracker.complete(2)

        with patch("ingestion.scheduler.run_custom_ingestion", side_effect=fake_run) as run:
            result = job_custom_ingestion({"topic": "gnn", "limit": 1}, "job-1")

        run.assert_called_once_with("gnn", 1)
        assert result["papers_added"] == 1
        assert result["claims_added"] == 4
        assert result["contradictions_found"] == 2

    def test_ingestion_failure_propagates_to_the_job(self, memory_store):
        """A failing pipeline must mark the job failed, not completed."""
        from jobs import backend
        from jobs.tasks import run_job

        memory_store.create("job-1", backend.JOB_CUSTOM_INGESTION)
        with patch("ingestion.scheduler.run_custom_ingestion",
                   side_effect=RuntimeError("arxiv down")):
            with pytest.raises(RuntimeError):
                run_job(backend.JOB_CUSTOM_INGESTION, "job-1",
                        {"topic": "gnn", "limit": 1})

        assert memory_store.get("job-1")["status"] == STATUS_FAILED

    def test_scheduler_dispatches_to_the_queue(self, memory_store, monkeypatch):
        """With a queue available, ticks enqueue instead of ingesting in-process."""
        from ingestion import scheduler

        monkeypatch.setattr("jobs.backend.backend_name", lambda: "rq")
        with patch("jobs.backend.submit", return_value=("job-1", "rq")) as submitted:
            scheduler._dispatch_ingestion()

        assert submitted.call_args[0][0] == "ingestion"
        assert memory_store.get("job-1") is None  # submit was stubbed out

    def test_scheduler_skips_tick_when_ingestion_is_active(self, monkeypatch):
        from ingestion import scheduler
        from jobs.backend import JobConflictError

        monkeypatch.setattr("jobs.backend.backend_name", lambda: "rq")
        with patch("jobs.backend.submit", side_effect=JobConflictError("busy")), \
             patch.object(scheduler, "_ingestion_job") as inline_job:
            scheduler._dispatch_ingestion()

        inline_job.assert_not_called()

    def test_scheduler_runs_inline_without_a_queue(self, monkeypatch):
        from ingestion import scheduler

        monkeypatch.setattr("jobs.backend.backend_name", lambda: "inline")
        with patch.object(scheduler, "_ingestion_job",
                          return_value={"papers_added": 1}) as inline_job:
            scheduler._dispatch_ingestion()

        inline_job.assert_called_once()


# ─── Cross-process progress mirror ────────────────────────────────────────────

class TestProgressMirror:
    def test_worker_progress_is_visible_to_another_process(self, monkeypatch):
        fake = FakeRedis()
        monkeypatch.setattr("jobs.redis_conn.is_configured", lambda: True)
        monkeypatch.setattr("jobs.redis_conn.get_redis", lambda: fake)

        from ingestion.progress import IngestionProgressTracker

        worker = IngestionProgressTracker()
        worker.start("topic x", 2)
        worker.update_status("processing", "Ingesting papers")
        worker.start_paper(1, "2301.00001", "A paper")
        worker.finish_paper(3.0, 2)

        # A second tracker stands in for the API process: idle locally.
        api_view = IngestionProgressTracker()
        snapshot = api_view.get_progress()

        assert snapshot["status"] == "processing"
        assert snapshot["topic"] == "topic x"
        assert snapshot["papers_added"] == 1
        assert snapshot["claims_added"] == 2

    def test_local_state_wins_when_this_process_owns_the_run(self, monkeypatch):
        fake = FakeRedis()
        monkeypatch.setattr("jobs.redis_conn.is_configured", lambda: True)
        monkeypatch.setattr("jobs.redis_conn.get_redis", lambda: fake)

        from ingestion.progress import IngestionProgressTracker

        tracker = IngestionProgressTracker()
        tracker.start("mine", 1)
        fake.data["axion:ingestion:progress"] = json.dumps(
            {"status": "completed", "topic": "someone else"}
        )

        snapshot = tracker.get_progress()
        assert snapshot["topic"] == "mine"
        assert snapshot["status"] == "searching"

    def test_idle_without_redis_is_just_idle(self, monkeypatch):
        monkeypatch.setattr("jobs.redis_conn.is_configured", lambda: False)
        from ingestion.progress import IngestionProgressTracker

        assert IngestionProgressTracker().get_progress()["status"] == "idle"

    def test_progress_without_configured_redis_never_persists(self, monkeypatch):
        from ingestion.progress import IngestionProgressTracker

        monkeypatch.setattr("jobs.redis_conn.is_configured", lambda: False)
        monkeypatch.setattr("jobs.redis_conn.get_redis",
                            lambda: pytest.fail("must not touch Redis"))
        IngestionProgressTracker().start("topic", 1)  # must not raise


# ─── Redis connection helper ──────────────────────────────────────────────────

class TestRedisConn:
    def test_no_url_means_no_client(self, monkeypatch):
        from jobs import redis_conn

        monkeypatch.setattr("config.REDIS_URL", "")
        redis_conn.reset()
        assert redis_conn.is_configured() is False
        assert redis_conn.get_redis() is None

    def test_unreachable_redis_degrades_to_none(self, monkeypatch):
        from jobs import redis_conn

        monkeypatch.setattr("config.REDIS_URL", "redis://127.0.0.1:1/0")
        redis_conn.reset()
        assert redis_conn.is_configured() is True
        assert redis_conn.get_redis() is None

    def test_client_is_created_in_bytes_mode(self, monkeypatch):
        """Regression: RQ calls `.decode()` on values it reads back.

        A decoding client (`decode_responses=True`) made every worker crash on
        its first maintenance pass with
        ``'str' object has no attribute 'decode'``.
        """
        import redis

        captured = {}

        class FakeClient:
            def ping(self):
                return True

        def fake_from_url(url, **kwargs):
            captured.update(kwargs)
            return FakeClient()

        monkeypatch.setattr(redis.Redis, "from_url", staticmethod(fake_from_url))
        monkeypatch.setattr("config.REDIS_URL", "redis://localhost:6379/0")

        from jobs import redis_conn

        redis_conn.reset()
        try:
            assert redis_conn.get_redis() is not None
            assert captured["decode_responses"] is False
        finally:
            redis_conn.reset()

    def test_url_with_password_is_not_logged(self):
        from jobs.redis_conn import _safe

        assert "hunter2" not in _safe("redis://:hunter2@redis:6379/0")
        assert _safe("redis://redis:6379/0") == "redis://redis:6379/0"


class TestRedisStoreBytesMode:
    def test_list_recent_decodes_byte_ids(self):
        """ZSET members come back as bytes; building keys from them must work."""
        from jobs.store import RedisJobStore

        fake = FakeRedis()
        store = RedisJobStore(fake, ttl=60)
        store.create("job-1", "query")
        store.create("job-2", "query")

        ids = [record["id"] for record in store.list_recent(limit=5)]
        assert sorted(ids) == ["job-1", "job-2"]

    def test_list_recent_returns_newest_first(self):
        from jobs.store import RedisJobStore

        fake = FakeRedis()
        store = RedisJobStore(fake, ttl=60)
        store.create("older", "query")
        import time as _time

        _time.sleep(0.01)
        store.create("newer", "query")

        assert [r["id"] for r in store.list_recent(limit=5)] == ["newer", "older"]

    def test_update_round_trips_through_bytes(self):
        from jobs.store import RedisJobStore, STATUS_RUNNING

        fake = FakeRedis()
        store = RedisJobStore(fake, ttl=60)
        store.create("job-1", "query")
        store.update("job-1", status=STATUS_RUNNING, started_at=1.5)

        record = store.get("job-1")
        assert record["status"] == STATUS_RUNNING
        assert record["started_at"] == 1.5


# ─── Worker class selection ───────────────────────────────────────────────────

class TestWorkerClass:
    def test_uses_the_forking_worker_when_available(self, monkeypatch):
        import os

        from jobs.worker import _worker_class

        monkeypatch.setattr(os, "fork", lambda: None, raising=False)
        assert _worker_class().__name__ == "Worker"

    def test_falls_back_to_simple_worker_without_fork(self, monkeypatch):
        """Windows has no os.fork; the worker must still be able to start."""
        import os

        from jobs.worker import _worker_class

        monkeypatch.delattr(os, "fork", raising=False)
        assert _worker_class().__name__ == "SimpleWorker"
