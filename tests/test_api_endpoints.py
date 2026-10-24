"""
HTTP-layer tests via FastAPI's TestClient.

These exercise the app through its real routing/middleware stack (unlike
`test_api_regressions.py`, which calls the endpoint functions directly).
Everything here is offline: datastores are patched, and the rate limiter is
disabled so repeated requests cannot produce spurious 429s.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _disable_rate_limiter():
    """slowapi's in-memory counters persist across tests — switch it off."""
    from api.main import limiter

    previous = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = previous


# ─── Liveness / readiness ─────────────────────────────────────────────────────

def test_healthz_liveness_always_ok():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_lifespan_starts_and_serves_without_datastores():
    """Boot through the real lifespan handler; it must degrade, not crash."""
    with patch("config.SCHEDULER_ENABLED", False), \
         patch("graph.neo4j_client.run_query", side_effect=RuntimeError("neo4j down")), \
         patch("embeddings.store.collection_stats", side_effect=RuntimeError("chroma down")), \
         patch("graph.neo4j_queries.get_graph_stats", side_effect=RuntimeError("neo4j down")):
        with TestClient(app) as lifespan_client:
            assert lifespan_client.get("/healthz").json() == {"status": "ok"}


def test_health_degraded_when_datastores_down():
    with patch("graph.neo4j_queries.get_graph_stats", side_effect=RuntimeError("neo4j down")), \
         patch("embeddings.store.collection_stats", side_effect=RuntimeError("chroma down")):
        r = client.get("/api/health")

    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert body["neo4j"] == "disconnected"
    assert body["chromadb"] == "disconnected"


def test_health_ok_when_datastores_up():
    with patch("graph.neo4j_queries.get_graph_stats", return_value={"claims": 5}), \
         patch("embeddings.store.collection_stats", return_value={"count": 5}):
        r = client.get("/api/health")

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["claims"] == 5


# ─── Ingestion (offline) ──────────────────────────────────────────────────────

def test_ingestion_status_offline():
    from ingestion.progress import progress_tracker

    progress_tracker.reset()
    with patch("jobs.backend.active_ingestion_job", return_value=None):
        r = client.get("/api/ingestion/status")

    assert r.status_code == 200
    body = r.json()
    assert body["running"] is False
    assert body["new_papers"] == 0
    assert body["last_run"] is None


def test_ingestion_progress_offline():
    from ingestion.progress import progress_tracker

    progress_tracker.reset()
    with patch("jobs.backend.active_ingestion_job", return_value=None):
        r = client.get("/api/ingestion/progress")
    assert r.status_code == 200
    assert "status" in r.json()


def test_ingestion_progress_reports_queued_job():
    """A queued job with no worker claim yet must not look idle to the UI."""
    from ingestion.progress import progress_tracker

    progress_tracker.reset()
    queued = {"id": "abc123", "kind": "custom_ingestion", "status": "queued",
              "_payload": {"topic": "graph neural networks", "limit": 3}}
    with patch("jobs.backend.active_ingestion_job", return_value=queued):
        r = client.get("/api/ingestion/progress")

    body = r.json()
    assert body["status"] == "queued"
    assert body["running"] is True
    assert body["topic"] == "graph neural networks"
    assert body["percent"] > 0


def test_compute_endpoints_disabled_when_no_secret():
    with patch.multiple("config", API_KEY="", TRIGGER_SECRET=""):
        assert client.post("/api/ingestion/trigger").status_code == 503
        assert client.post("/api/query", json={"question": "hi"}).status_code == 503
        assert client.post("/api/confidence/recalculate").status_code == 503
        assert client.get("/api/jobs").status_code == 503


def test_trigger_rejects_missing_or_wrong_secret():
    with patch.multiple("config", API_KEY="", TRIGGER_SECRET="s3cret"):
        assert client.post("/api/ingestion/trigger").status_code == 401
        assert client.post(
            "/api/ingestion/trigger", headers={"x-trigger-secret": "nope"}
        ).status_code == 401
        with patch("jobs.backend.submit", return_value=("job-1", "rq")):
            r = client.post(
                "/api/ingestion/trigger", headers={"x-trigger-secret": "s3cret"}
            )
    assert r.status_code == 202
    assert r.json()["job_id"] == "job-1"


def test_compute_endpoints_require_api_key():
    """The LLM-backed endpoints must not be callable anonymously."""
    with patch.multiple("config", API_KEY="k3y", TRIGGER_SECRET=""):
        assert client.post("/api/query", json={"question": "hi"}).status_code == 401
        assert client.post(
            "/api/query", json={"question": "hi"}, headers={"x-api-key": "wrong"}
        ).status_code == 401
        assert client.post("/api/confidence/recalculate").status_code == 401
        assert client.post("/api/experiments/abc/design").status_code == 401
        assert client.get("/api/jobs/whatever").status_code == 401


def test_query_queues_a_job_and_returns_202():
    with patch.multiple("config", API_KEY="k3y", TRIGGER_SECRET=""), \
         patch("jobs.backend.submit", return_value=("job-9", "rq")) as submitted:
        r = client.post(
            "/api/query", json={"question": "hi"}, headers={"x-api-key": "k3y"}
        )
    assert r.status_code == 202
    assert r.json() == {"job_id": "job-9", "status": "queued", "backend": "rq"}
    assert submitted.call_args[0][1] == {"question": "hi"}


def test_query_rejects_blank_question_before_queueing():
    with patch.multiple("config", API_KEY="k3y", TRIGGER_SECRET=""), \
         patch("jobs.backend.submit") as submitted:
        r = client.post(
            "/api/query", json={"question": "   "}, headers={"x-api-key": "k3y"}
        )
    assert r.status_code == 400
    submitted.assert_not_called()


def test_ingestion_conflict_returns_409():
    from jobs.backend import JobConflictError

    with patch.multiple("config", API_KEY="k3y", TRIGGER_SECRET=""), \
         patch("jobs.backend.submit", side_effect=JobConflictError("already running")):
        r = client.post("/api/ingestion/custom",
                        json={"topic": "gnn", "limit": 2},
                        headers={"x-api-key": "k3y"})
    assert r.status_code == 409


def test_job_status_endpoint_returns_record():
    record = {"id": "job-1", "kind": "query", "status": "completed",
              "result": {"report": "done"}, "_payload": {"question": "secret"}}
    with patch.multiple("config", API_KEY="k3y", TRIGGER_SECRET=""), \
         patch("jobs.store.get_job_store") as store:
        store.return_value.get.return_value = record
        r = client.get("/api/jobs/job-1", headers={"x-api-key": "k3y"})

    assert r.status_code == 200
    body = r.json()
    assert body["result"] == {"report": "done"}
    # Internal payloads must never be echoed back to the client.
    assert "_payload" not in body


def test_job_status_endpoint_404s_for_unknown_job():
    with patch.multiple("config", API_KEY="k3y", TRIGGER_SECRET=""), \
         patch("jobs.store.get_job_store") as store:
        store.return_value.get.return_value = None
        r = client.get("/api/jobs/nope", headers={"x-api-key": "k3y"})
    assert r.status_code == 404


def test_job_list_is_key_guarded_and_clamps_limit():
    records = [
        {"id": "job-2", "kind": "query", "status": "queued", "_payload": {}},
        {"id": "job-1", "kind": "query", "status": "completed"},
    ]
    with patch.multiple("config", API_KEY="k3y", TRIGGER_SECRET=""), \
         patch("jobs.store.get_job_store") as store:
        store.return_value.list_recent.return_value = records

        r = client.get("/api/jobs", headers={"x-api-key": "k3y"})

        assert r.status_code == 200
        body = r.json()
        assert [job["id"] for job in body["jobs"]] == ["job-2", "job-1"]
        assert all("_payload" not in job for job in body["jobs"])

        # An absurd limit must not be forwarded to the store.
        client.get("/api/jobs?limit=99999", headers={"x-api-key": "k3y"})
        assert store.return_value.list_recent.call_args.args[0] == 100

        # Missing key is 401 while the server has a key configured. Keep this
        # request inside the patch: in CI there is no .env, so an unpatched
        # config would fail closed with 503 instead.
        without_key = client.get("/api/jobs")
        assert without_key.status_code == 401


# ─── Metrics ──────────────────────────────────────────────────────────────────

def test_metrics_endpoint_returns_summary():
    r = client.get("/api/metrics")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)
