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
    with patch("ingestion.scheduler.is_running", return_value=False), \
         patch("ingestion.scheduler.get_run_log", return_value=[]):
        r = client.get("/api/ingestion/status")

    assert r.status_code == 200
    body = r.json()
    assert body["running"] is False
    assert body["new_papers"] == 0
    assert body["last_run"] is None


def test_ingestion_progress_offline():
    r = client.get("/api/ingestion/progress")
    assert r.status_code == 200
    assert "status" in r.json()


def test_compute_endpoints_disabled_when_no_secret():
    with patch.multiple("config", API_KEY="", TRIGGER_SECRET=""):
        assert client.post("/api/ingestion/trigger").status_code == 503
        assert client.post("/api/query", json={"question": "hi"}).status_code == 503
        assert client.post("/api/confidence/recalculate").status_code == 503


def test_trigger_rejects_missing_or_wrong_secret():
    with patch.multiple("config", API_KEY="", TRIGGER_SECRET="s3cret"):
        assert client.post("/api/ingestion/trigger").status_code == 401
        assert client.post(
            "/api/ingestion/trigger", headers={"x-trigger-secret": "nope"}
        ).status_code == 401
        with patch("ingestion.scheduler.trigger_now"):
            assert client.post(
                "/api/ingestion/trigger", headers={"x-trigger-secret": "s3cret"}
            ).status_code == 200


def test_compute_endpoints_require_api_key():
    """The LLM-backed endpoints must not be callable anonymously."""
    with patch.multiple("config", API_KEY="k3y", TRIGGER_SECRET=""):
        assert client.post("/api/query", json={"question": "hi"}).status_code == 401
        assert client.post(
            "/api/query", json={"question": "hi"}, headers={"x-api-key": "wrong"}
        ).status_code == 401
        assert client.post("/api/confidence/recalculate").status_code == 401
        assert client.post("/api/experiments/abc/design").status_code == 401


def test_query_accepts_valid_api_key():
    with patch.multiple("config", API_KEY="k3y", TRIGGER_SECRET=""), \
         patch("agents.coordinator_v2.run", return_value={
             "report": "r", "raw": {"confidence_in_answer": "medium"},
             "iterations": 1, "plan": {"sub_queries": []}, "reflection_log": [],
         }):
        r = client.post(
            "/api/query", json={"question": "hi"}, headers={"x-api-key": "k3y"}
        )
    assert r.status_code == 200


# ─── Metrics ──────────────────────────────────────────────────────────────────

def test_metrics_endpoint_returns_summary():
    r = client.get("/api/metrics")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)
