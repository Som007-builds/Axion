# tests/test_gap_sources.py
"""Canonical research-gap source taxonomy and API filtering."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from api.gap_sources import count_gap_sources, normalize_gap_source
from api.main import get_gaps


class TestNormalizeGapSource:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("cluster", "cluster"),
            ("future_work", "future_work"),
            (" Future_Work ", "future_work"),
            ("sqlite_migration", "legacy_import"),
            ("legacy", "legacy_import"),
            ("legacy_import", "legacy_import"),
            ("llm_synthesized", "unknown"),
            ("semantic", "unknown"),
            ("something_else", "unknown"),
            (None, "unknown"),
            ("", "unknown"),
        ],
    )
    def test_normalizes_only_explicit_values(self, raw, expected):
        assert normalize_gap_source(raw) == expected

    def test_counts_cover_canonical_taxonomy(self):
        gaps = [
            {"source": "cluster"},
            {"source": "future_work"},
            {"source": "sqlite_migration"},
            {"source": None},
            {"source": "cluster"},
        ]
        counts = count_gap_sources(gaps)
        assert counts == {
            "all": 5,
            "cluster": 2,
            "future_work": 1,
            "legacy_import": 1,
            "unknown": 1,
        }


SAMPLE_GAPS = [
    {
        "id": "g-cluster",
        "text": "Does the method generalise?",
        "source": "cluster",
        "confidence": 0.8,
        "related_claims": ["c1", "missing"],
    },
    {
        "id": "g-legacy",
        "text": "What was never recorded?",
        "source": "sqlite_migration",
        "confidence": None,
        "related_claims": ["c2"],
    },
    {
        "id": "g-unknown",
        "text": "Which values are unsupported?",
        "source": "llm_synthesized",
        "confidence": None,
        "related_claims": [],
    },
]

CLAIM_REFS = {
    "c1": {
        "id": "c1",
        "text": "The method was tested on English only.",
        "section": "Limitations",
        "confidence": 0.7,
        "arxiv_id": "2401.00001",
        "paper_title": "A Paper",
    },
    "c2": {
        "id": "c2",
        "text": "The import has no extraction provenance.",
        "section": "Methods",
        "confidence": 0.5,
        "arxiv_id": "2401.00002",
        "paper_title": "Another Paper",
    },
}


class TestGapApi:
    def _call(self, source=None):
        with patch("graph.neo4j_queries.get_gaps", return_value=SAMPLE_GAPS), \
             patch("graph.neo4j_queries.get_claim_references", return_value=CLAIM_REFS):
            return get_gaps(source=source)

    def test_all_gaps_normalized_and_enriched(self):
        out = self._call()
        assert out["total"] == 3
        assert out["corpus_total"] == 3
        assert out["source_counts"] == {
            "all": 3,
            "cluster": 1,
            "future_work": 0,
            "legacy_import": 1,
            "unknown": 1,
        }
        by_id = {g["id"]: g for g in out["gaps"]}
        assert by_id["g-cluster"]["source"] == "cluster"
        assert by_id["g-cluster"]["source_label"] == "Cluster-derived"
        assert by_id["g-cluster"]["confidence"] == 0.8
        assert by_id["g-cluster"]["related_claim_details"][0]["text"].startswith(
            "The method was tested"
        )
        # A dangling link keeps the ID but never invents claim text.
        assert len(by_id["g-cluster"]["related_claim_details"]) == 1
        assert by_id["g-legacy"]["source"] == "legacy_import"
        assert by_id["g-legacy"]["source_raw"] == "sqlite_migration"
        assert by_id["g-unknown"]["source"] == "unknown"

    def test_filter_is_applied_server_side(self):
        out = self._call("legacy_import")
        assert out["total"] == 1
        assert out["gaps"][0]["id"] == "g-legacy"
        # Counts still describe the unfiltered corpus.
        assert out["corpus_total"] == 3
        assert out["source_counts"]["cluster"] == 1

    def test_unknown_filter_is_supported(self):
        out = self._call("unknown")
        assert [g["id"] for g in out["gaps"]] == ["g-unknown"]

    def test_unsupported_filter_is_rejected(self):
        with pytest.raises(HTTPException) as exc:
            self._call("semantic")
        assert exc.value.status_code == 400
        assert "legacy_import" in exc.value.detail
