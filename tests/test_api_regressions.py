# tests/test_api_regressions.py
"""
Regression tests for P0 backend fixes:

  * ingestion trigger secret fails closed when unconfigured
  * /api/temporal/disputes maps the real temporal.py schema
  * /api/temporal/evolution no longer fabricates per-year data
"""
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from api.main import (
    get_disputes,
    get_evolution,
    require_trigger_secret,
    require_write_access,
    ingestion_status,
)


# ─── Write/compute auth (fail-closed) ─────────────────────────────────────────

class TestWriteAccess:

    def test_no_secrets_configured_disables_endpoints(self):
        with patch.multiple("config", API_KEY="", TRIGGER_SECRET=""):
            with pytest.raises(HTTPException) as exc:
                require_write_access(x_api_key=None, x_trigger_secret=None)
        assert exc.value.status_code == 503

    def test_missing_key_is_rejected(self):
        with patch.multiple("config", API_KEY="k3y", TRIGGER_SECRET=""):
            with pytest.raises(HTTPException) as exc:
                require_write_access(x_api_key=None, x_trigger_secret=None)
        assert exc.value.status_code == 401

    def test_wrong_key_is_rejected(self):
        with patch.multiple("config", API_KEY="k3y", TRIGGER_SECRET=""):
            with pytest.raises(HTTPException) as exc:
                require_write_access(x_api_key="nope", x_trigger_secret=None)
        assert exc.value.status_code == 401

    def test_correct_api_key_passes(self):
        with patch.multiple("config", API_KEY="k3y", TRIGGER_SECRET=""):
            require_write_access(x_api_key="k3y", x_trigger_secret=None)  # no raise

    def test_legacy_trigger_secret_still_accepted(self):
        with patch.multiple("config", API_KEY="", TRIGGER_SECRET="s3cret"):
            require_write_access(x_api_key=None, x_trigger_secret="s3cret")  # no raise

    def test_legacy_wrapper_still_fails_closed(self):
        with patch.multiple("config", API_KEY="", TRIGGER_SECRET=""):
            with pytest.raises(HTTPException) as exc:
                require_trigger_secret(None)
        assert exc.value.status_code == 503


# ─── Temporal disputes mapping ────────────────────────────────────────────────

class TestDisputeMapping:

    def test_maps_real_temporal_schema(self):
        fake = {
            "disputes": [
                {
                    "description": "Does X help?",
                    "first_appeared": 2021,
                    "status": "resolved",
                    "resolution": "X helps",
                    "resolution_year": 2023,
                    "related_claim_ids": ["4:a:1", "4:b:2"],
                }
            ],
            "claim_text_by_id": {"4:a:1": "X helps", "4:b:2": "X does not help"},
        }
        with patch("agents.temporal.get_contradiction_timeline", return_value=fake):
            out = get_disputes("x")

        d = out["disputes"][0]
        assert d["topic"] == "Does X help?"
        assert d["start_year"] == 2021
        assert d["end_year"] == 2023
        assert d["resolved"] is True
        assert d["resolution"] == "X helps"
        assert d["key_claims"] == ["X helps", "X does not help"]

    def test_handles_missing_fields(self):
        fake = {"disputes": [{"description": "Unresolved", "status": "active"}]}
        with patch("agents.temporal.get_contradiction_timeline", return_value=fake):
            out = get_disputes("x")

        d = out["disputes"][0]
        assert d["start_year"] is None
        assert d["end_year"] is None
        assert d["resolved"] is False
        assert d["key_claims"] == []

    def test_empty_timeline(self):
        with patch("agents.temporal.get_contradiction_timeline", return_value={"disputes": []}):
            out = get_disputes("x")
        assert out["disputes"] == []


# ─── Temporal evolution mapping ───────────────────────────────────────────────

class TestEvolutionMapping:

    def test_uses_per_year_confidence_and_skips_bad_years(self):
        fake = {
            "yearly_positions": [
                {"year": 2022, "position": "field believed A", "confidence": 0.7,
                 "key_claim_arxiv_ids": ["2401.1"]},
                {"year": "not-a-year", "position": "garbage"},
                {"year": 2023, "position": "field shifted to B"},
            ],
            "overall_narrative": "arc",
            "current_status": "settled",
            "confidence": 0.9,
        }
        with patch("agents.temporal.get_consensus_evolution", return_value=fake):
            out = get_evolution("topic", 2020, 2025)

        assert [p["year"] for p in out["yearly_positions"]] == [2022, 2023]
        assert out["yearly_positions"][0]["confidence"] == 0.7
        # missing per-year confidence falls back to the top-level value
        assert out["yearly_positions"][1]["confidence"] == 0.9
        assert out["yearly_positions"][0]["key_papers"] == ["2401.1"]


# ─── Ingestion status running flag ────────────────────────────────────────────

class TestIngestionStatus:

    def test_running_reflects_scheduler_state(self):
        with patch("ingestion.scheduler.is_running", return_value=True), \
             patch("ingestion.scheduler.get_run_log", return_value=[]):
            out = ingestion_status()
        assert out["running"] is True

    def test_idle_when_nothing_running(self):
        with patch("ingestion.scheduler.is_running", return_value=False), \
             patch("ingestion.scheduler.get_run_log", return_value=[]):
            out = ingestion_status()
        assert out["running"] is False
        assert out["last_run"] is None

    def test_reports_last_run_stats(self):
        fake_log = [{"timestamp": "2026-10-16T00:00:00", "papers_added": 3, "claims_added": 12}]
        with patch("ingestion.scheduler.is_running", return_value=False), \
             patch("ingestion.scheduler.get_run_log", return_value=fake_log):
            out = ingestion_status()
        assert out["new_papers"] == 3
        assert out["new_claims"] == 12
        assert out["last_run"] == "2026-10-16T00:00:00"
