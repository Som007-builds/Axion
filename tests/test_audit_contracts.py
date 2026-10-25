# tests/test_audit_contracts.py
"""Contract tests for the evidence/confidence/count fixes."""

import json
from unittest.mock import patch

from api.main import get_contradictions, get_graph_data
from agents.temporal import get_contradiction_timeline
from jobs.tasks import format_query_output


class TestTemporalDisputes:
    def test_year_range_is_forwarded(self):
        with patch("agents.temporal.get_claims_by_year_range", return_value=[]) as mock_claims:
            out = get_contradiction_timeline("topic", 2021, 2023)
        mock_claims.assert_called_once_with("topic", 2021, 2023, n_results=40)
        assert out["year_start"] == 2021
        assert out["year_end"] == 2023
        assert out["candidate_claim_count"] == 0

    def test_stale_chroma_id_is_resolved_by_exact_text(self):
        chroma_matches = [{
            "doc_id": "claim_57",
            "text": "X helps small models",
            "metadata": {"arxiv_id": "2401.00001", "paper_year": 2022},
            "distance": 0.1,
        }]
        graph_claims = [{
            "id": "4:db:713",
            "text": "X helps small models",
            "arxiv_id": "2401.00001",
            "paper_year": 2022,
            "paper_title": "Paper A",
        }]
        contradictions = [{
            "id": "r1",
            "claim_a_id": "4:db:713",
            "claim_b_id": "4:db:999",
            "claim_a": "X helps small models",
            "claim_b": "X does not help small models",
            "explanation": "Opposite conclusions",
            "confidence": 0.82,
        }]
        llm = json.dumps({"disputes": [{
            "description": "Whether X helps small models",
            "status": "active",
            "related_claim_ids": ["4:db:713", "4:db:999"],
        }]})
        with patch("agents.temporal.find_similar_claims", return_value=chroma_matches), \
             patch("agents.temporal.get_all_claims", return_value=graph_claims), \
             patch("agents.temporal.get_contradictions", return_value=contradictions), \
             patch("agents.temporal.call_llm", return_value=llm):
            out = get_contradiction_timeline("small models", 2020, 2024)

        assert len(out["disputes"]) == 1
        assert out["disputes"][0]["description"] == "Whether X helps small models"
        assert out["contradiction_count"] == 1
        assert out["candidate_claim_count"] == 1
        assert out["claim_text_by_id"]["4:db:713"] == "X helps small models"

    def test_empty_result_explicitly_does_not_prove_consensus(self):
        with patch("agents.temporal.get_claims_by_year_range", return_value=[]):
            out = get_contradiction_timeline("silent topic", 2020, 2026)
        assert "does not establish" in out["summary"]


def _contradiction_row():
    return {
        "id": "4:db:r1",
        "explanation": "The two claims report opposite directions.",
        "confidence": 0.82,
        "claim_a": "Method A improves accuracy.",
        "claim_a_section": "Results",
        "claim_a_confidence": 0.9,
        "claim_a_evidence_span": "Table 2 shows +3.1 points.",
        "claim_a_subject": "Method A",
        "claim_a_predicate": "improves",
        "claim_a_object_val": "accuracy",
        "claim_a_metric": "accuracy",
        "claim_a_direction": "increase",
        "claim_a_conditions": '{"dataset": "MMLU"}',
        "paper_a": "Paper A",
        "paper_a_arxiv_id": "2401.00001",
        "claim_b": "Method A does not improve accuracy.",
        "claim_b_section": "Results",
        "claim_b_confidence": 0.8,
        "claim_b_evidence_span": "Table 3 shows no significant gain.",
        "claim_b_subject": "Method A",
        "claim_b_predicate": "does not improve",
        "claim_b_object_val": "accuracy",
        "claim_b_metric": "accuracy",
        "claim_b_direction": "no_change",
        "claim_b_conditions": "{}",
        "paper_b": "Paper B",
        "paper_b_arxiv_id": "2401.00002",
        "claim_a_id": "4:db:713",
        "claim_b_id": "4:db:999",
    }


class TestContradictionContract:
    def test_separates_matching_total_corpus_and_shown_counts(self):
        rows = [_contradiction_row(), {**_contradiction_row(), "id": "4:db:r2",
                                        "confidence": 0.1}]
        with patch("graph.neo4j_queries.get_contradictions", return_value=rows), \
             patch("agents.experiment_recommender.get_experiment_for_contradiction",
                   return_value=None):
            out = get_contradictions(min_confidence=0.35, limit=1)

        assert out["total"] == 1          # matches threshold
        assert out["corpus_total"] == 2   # every relationship
        assert out["shown"] == 1          # payload cap
        item = out["contradictions"][0]
        assert item["claim_a"]["evidence_span"] == "Table 2 shows +3.1 points."
        assert item["claim_a"]["subject"] == "Method A"
        assert item["claim_a"]["paper_title"] == "Paper A"
        assert item["claim_b"]["conditions"] == "{}"


class TestGraphContract:
    def test_only_papers_linked_to_selected_claims_are_returned(self):
        claims = [
            {
                "id": "c1",
                "text": "Claim one",
                "section": "Results",
                "confidence": 0.8,
                "arxiv_id": "2401.00001",
                "paper_title": "Paper A",
                "year": 2024,
            },
            {
                "id": "c2",
                "text": "Claim two",
                "section": "Discussion",
                "confidence": 0.6,
                "arxiv_id": "2401.00001",
                "paper_title": "Paper A",
                "year": 2024,
            },
            {
                "id": "c3",
                "text": "Claim three",
                "section": "Results",
                "confidence": 0.7,
                "arxiv_id": "2401.00002",
                "paper_title": "Paper B",
                "year": 2025,
            },
        ]
        gaps = [{
            "id": "g1",
            "text": "An unresolved question",
            "source": "sqlite_migration",
            "confidence": 0.5,
            "related_claim_ids": [],
        }]
        with patch(
            "graph.neo4j_client.run_query",
            side_effect=[claims, [], [], gaps],
        ):
            out = get_graph_data(limit_claims=3)

        papers = [node for node in out["nodes"] if node["type"] == "paper"]
        assert len(papers) == 2
        assert {p["arxiv_id"] for p in papers} == {"2401.00001", "2401.00002"}

        gap = next(node for node in out["nodes"] if node["type"] == "gap")
        assert gap["source"] == "legacy_import"

        node_ids = {node["id"] for node in out["nodes"]}
        assert len(out["edges"]) == 3
        assert all(
            edge["source"] in node_ids and edge["target"] in node_ids
            for edge in out["edges"]
        )


class TestQueryOutputCounts:
    def test_reports_retrieved_context_and_model_label(self):
        output = {
            "report": "# report",
            "raw": {
                "consensus": [{"finding": "A", "citations": ["2401.00001"]}],
                "confidence_in_answer": "medium",
                "confidence_reason": "Single-paper evidence",
            },
            "iterations": 2,
            "plan": {"sub_queries": ["q1"]},
            "reflection_log": [],
            "context": {
                "claims": [{"id": "1"}, {"id": "2"}],
                "contradictions": [{"id": "r1"}],
                "gaps": [],
            },
        }
        out = format_query_output(output)
        assert out["confidence_label"] == "medium"
        assert out["source_count"] == 1
        assert out["claim_count"] == 2
        assert out["contradiction_count"] == 1
        assert out["gap_count"] == 0

    def test_unknown_label_is_not_mapped_to_a_numeric_claim(self):
        out = format_query_output({"raw": {}, "context": {}})
        assert out["confidence_label"] == "unknown"
        assert out["sources"] == []
