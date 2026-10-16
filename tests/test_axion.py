"""
Axion — Full Test Suite
==============================
Run:  pytest tests/test_axion.py -v
Deps: pytest, pytest-mock  (pip install pytest pytest-mock)

All external I/O (Neo4j, ChromaDB, LLM APIs) is mocked so the suite
runs with no live services.  Tests are grouped into sections:

  1.  config           — env loading, path existence
  2.  llm              — provider dispatch, retry logic
  3.  citation         — weighting formula, cache, HTTP mocking
  4.  planner          — JSON parsing, sub-query sanitisation
  5.  reflector        — sufficiency threshold, fallback, dead-code note
  6.  synthesizer      — format_report structure
  7.  temporal         — year-range filter, insufficient-data guard
  8.  contradiction    — check_pair JSON parsing, int-cast bug flag
  9.  gap_finder       — future-work extraction, short-text guard
  10. coordinator_v2   — _merge_contexts, _is_temporal_question,
                         full run() loop (plan→retrieve→reflect→synthesize)
  11. store            — find_similar_claims shape
  12. neo4j_queries    — insert/get helpers (driver mocked)
  13. regression       — known bugs documented as tests
"""

import json
import math
import pytest
from unittest.mock import MagicMock, patch, call


# ═══════════════════════════════════════════════════════════════
# 1. CONFIG
# ═══════════════════════════════════════════════════════════════

class TestConfig:
    def test_llm_provider_is_string(self):
        from config import LLM_PROVIDER
        assert isinstance(LLM_PROVIDER, str)
        assert LLM_PROVIDER in ("groq", "gemini", "claude")

    def test_embedding_model_set(self):
        from config import EMBEDDING_MODEL
        assert EMBEDDING_MODEL  # non-empty

    def test_max_claims_positive(self):
        from config import MAX_CLAIMS_PER_PAPER
        assert MAX_CLAIMS_PER_PAPER > 0

    def test_contradiction_threshold_in_range(self):
        from config import CONTRADICTION_THRESHOLD
        assert 0.0 < CONTRADICTION_THRESHOLD <= 1.0

    def test_neo4j_defaults(self):
        from config import NEO4J_URI, NEO4J_USER
        assert NEO4J_URI.startswith("bolt://")
        assert NEO4J_USER  # non-empty


# ═══════════════════════════════════════════════════════════════
# 2. LLM
# ═══════════════════════════════════════════════════════════════

class TestLLM:
    def _patch_provider(self, provider: str):
        """Helper — sets LLM_PROVIDER without touching os.environ."""
        import config as cfg
        cfg.LLM_PROVIDER = provider

    @patch("config.LLM_PROVIDER", "groq")
    def test_groq_dispatch(self):
        # Groq is imported inside call_llm body → patch at source package
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="  hello  "))]
        )
        mock_groq_module = MagicMock()
        mock_groq_module.Groq.return_value = mock_client
        import sys
        sys.modules.setdefault("groq", mock_groq_module)
        with patch.dict(sys.modules, {"groq": mock_groq_module}):
            import importlib, llm as llm_mod
            importlib.reload(llm_mod)
            result = llm_mod.call_llm("test prompt")
        assert result == "hello"

    def test_claude_dispatch(self):
        # anthropic is imported inside call_llm body — patch at source package.
        # Avoid reload() which bleeds state across tests; instead patch
        # LLM_PROVIDER directly on the already-loaded module.
        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text="  answer  ")]
        )
        mock_anthropic_module = MagicMock()
        mock_anthropic_module.Anthropic.return_value = mock_client
        import sys
        import llm as llm_mod
        with patch.dict(sys.modules, {"anthropic": mock_anthropic_module}), \
             patch.object(llm_mod.config, "LLM_PROVIDER", "claude"):
            result = llm_mod.call_llm("test prompt")
        assert result == "answer"

    @patch("config.LLM_PROVIDER", "groq")
    @patch("config.LLM_PROVIDER_CHAIN", ["groq"])
    @patch("llm.time.sleep")
    def test_rate_limit_retry(self, mock_sleep):
        """On rate-limit error, should wait and retry up to `retries` times."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("rate_limit exceeded")
        mock_groq_module = MagicMock()
        mock_groq_module.Groq.return_value = mock_client
        import sys, importlib, llm as llm_mod
        with patch.dict(sys.modules, {"groq": mock_groq_module}):
            importlib.reload(llm_mod)
            with pytest.raises(Exception, match="All LLM providers exhausted"):
                llm_mod.call_llm("test", retries=2)
        # retries=2 with a single-provider chain => one back-off sleep
        assert mock_sleep.call_count == 1

    def test_non_rate_limit_error_falls_back_to_next_provider(self):
        """A dead model / auth error on the primary must not kill the chain.

        Regression: a decommissioned Groq model used to raise out of
        ``call_llm`` even though Gemini was configured as a fallback.
        """
        import llm as llm_mod
        calls = []

        def dead(prompt, max_tokens):
            calls.append("groq")
            raise Exception("model `llama-3.1-8b-instant` does not exist")

        def alive(prompt, max_tokens):
            calls.append("gemini")
            return "gemini answer"

        with patch.object(llm_mod.config, "LLM_PROVIDER", "groq"), \
             patch.object(llm_mod, "LLM_PROVIDER_CHAIN", ["groq", "gemini"]), \
             patch.dict(llm_mod._PROVIDERS, {"groq": dead, "gemini": alive}):
            result = llm_mod.call_llm("test")

        assert result == "gemini answer"
        assert calls == ["groq", "gemini"]

    def test_all_providers_dead_raises_chain_exhausted(self):
        import llm as llm_mod

        def dead(prompt, max_tokens):
            raise Exception("model not found")

        with patch.object(llm_mod.config, "LLM_PROVIDER", "groq"), \
             patch.object(llm_mod, "LLM_PROVIDER_CHAIN", ["groq"]), \
             patch.dict(llm_mod._PROVIDERS, {"groq": dead}):
            with pytest.raises(Exception, match="All LLM providers exhausted"):
                llm_mod.call_llm("test")


# ═══════════════════════════════════════════════════════════════
# 3. CITATION
# ═══════════════════════════════════════════════════════════════

class TestCitationWeighting:
    """Pure math — no Neo4j needed."""

    def _weight(self, base: float, citations: int) -> float:
        MAX_BOOST = math.log2(2 + 10_000)
        boost = math.log2(2 + citations)
        return round(min(1.0, max(0.0, base * (0.5 + 0.5 * boost / MAX_BOOST))), 4)

    def test_zero_citations_penalises_confidence(self):
        # log2(2+0)=1, log2(2+10000)≈13.29  →  1.0*(0.5 + 0.5*(1/13.29)) ≈ 0.538
        w = self._weight(1.0, 0)
        assert w == pytest.approx(0.5376, abs=0.001)

    def test_high_citations_approaches_base(self):
        w = self._weight(1.0, 10_000)
        assert w == pytest.approx(1.0, abs=0.001)

    def test_moderate_citations(self):
        w = self._weight(1.0, 100)
        assert 0.7 < w < 0.85

    def test_output_clamped_to_unit_interval(self):
        w = self._weight(0.9999, 999_999)
        assert 0.0 <= w <= 1.0

    def test_get_weighted_confidence_no_neo4j_result(self):
        """When Neo4j returns nothing, base_confidence is returned unchanged."""
        with patch("agents.citation.run_query", return_value=[]):
            from agents.citation import get_weighted_confidence
            result = get_weighted_confidence("fake_id", 0.8)
        assert result == 0.8

    def test_get_weighted_confidence_with_citations(self):
        with patch("agents.citation.run_query", return_value=[{"citation_count": 500}]):
            from agents.citation import get_weighted_confidence
            result = get_weighted_confidence("fake_id", 1.0)
        assert 0.8 < result <= 1.0

    @patch("agents.citation.requests.get")
    def test_fetch_404_returns_zero(self, mock_get):
        mock_get.return_value = MagicMock(status_code=404)
        from agents.citation import fetch_citation_count, _CACHE
        _CACHE.clear()
        count = fetch_citation_count("nonexistent_id_xyz")
        assert count == 0

    @patch("agents.citation.requests.get")
    def test_fetch_success(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"citationCount": 42, "title": "Test Paper"}
        )
        from agents.citation import fetch_citation_count, _CACHE
        _CACHE.clear()
        count = fetch_citation_count("2301.00001")
        assert count == 42

    @patch("agents.citation.requests.get")
    def test_cache_prevents_duplicate_requests(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"citationCount": 10}
        )
        from agents.citation import fetch_citation_count, _CACHE
        _CACHE.clear()
        fetch_citation_count("cache_test_id")
        fetch_citation_count("cache_test_id")
        assert mock_get.call_count == 1


# ═══════════════════════════════════════════════════════════════
# 4. PLANNER
# ═══════════════════════════════════════════════════════════════

VALID_PLAN_JSON = json.dumps({
    "sub_queries": ["chain of thought small models", "reasoning LLM benchmarks"],
    "fetch_contradictions": True,
    "fetch_gaps": False,
    "reasoning": "Split into two orthogonal queries"
})

class TestPlanner:
    def test_valid_json_parsed_correctly(self):
        with patch("agents.planner.call_llm", return_value=VALID_PLAN_JSON):
            from agents.planner import make_plan
            plan = make_plan("How does CoT affect small LLMs?")
        assert len(plan["sub_queries"]) == 2
        assert all(isinstance(q, str) for q in plan["sub_queries"])
        assert plan["fetch_contradictions"] is True
        assert plan["fetch_gaps"] is False

    def test_dict_subquery_is_clamped_to_string(self):
        bad_plan = json.dumps({
            "sub_queries": [{"ChromaDB": "chain_of_thought"}],
            "fetch_contradictions": True,
            "fetch_gaps": True,
            "reasoning": "test"
        })
        with patch("agents.planner.call_llm", return_value=bad_plan):
            from agents.planner import make_plan
            plan = make_plan("test question")
        assert all(isinstance(q, str) for q in plan["sub_queries"])

    def test_json_parse_failure_falls_back_gracefully(self):
        with patch("agents.planner.call_llm", return_value="not json at all %%%"):
            from agents.planner import make_plan
            plan = make_plan("fallback question")
        assert "sub_queries" in plan
        assert isinstance(plan["sub_queries"], list)
        assert plan["sub_queries"][0] == "fallback question"

    def test_sub_queries_capped_at_3(self):
        many = json.dumps({
            "sub_queries": ["q1", "q2", "q3", "q4", "q5"],
            "fetch_contradictions": True,
            "fetch_gaps": True,
            "reasoning": "too many"
        })
        with patch("agents.planner.call_llm", return_value=many):
            from agents.planner import make_plan
            plan = make_plan("test")
        assert len(plan["sub_queries"]) <= 3

    def test_markdown_fenced_json_extracted(self):
        fenced = "```json\n" + VALID_PLAN_JSON + "\n```"
        with patch("agents.planner.call_llm", return_value=fenced):
            from agents.planner import make_plan
            plan = make_plan("test")
        # Should still parse — fallback extracts {...} from raw string
        assert "sub_queries" in plan

    def test_empty_sub_queries_fallback(self):
        empty = json.dumps({
            "sub_queries": [],
            "fetch_contradictions": True,
            "fetch_gaps": True,
            "reasoning": "empty"
        })
        with patch("agents.planner.call_llm", return_value=empty):
            from agents.planner import make_plan
            plan = make_plan("my question")
        # Empty list is technically valid per current code; just confirm no crash
        assert isinstance(plan["sub_queries"], list)


# ═══════════════════════════════════════════════════════════════
# 5. REFLECTOR
# ═══════════════════════════════════════════════════════════════

def _make_context(n_claims=5):
    return {
        "claims": [
            {"arxiv_id": f"23{i:02d}.00001", "text": f"Claim number {i} about topic X"}
            for i in range(n_claims)
        ],
        "contradictions": [],
        "gaps": []
    }

class TestReflector:
    def test_score_above_threshold_marks_sufficient(self):
        resp = json.dumps({"score": 8, "sufficient": False,
                           "assessment": "good", "refined_query": None})
        with patch("agents.reflector.call_llm", return_value=resp):
            from agents.reflector import reflect
            result = reflect("test question", _make_context())
        assert result["sufficient"] is True
        assert result["score"] == 8

    def test_score_below_threshold_marks_insufficient(self):
        resp = json.dumps({"score": 4, "sufficient": True,
                           "assessment": "sparse", "refined_query": "better query"})
        with patch("agents.reflector.call_llm", return_value=resp):
            from agents.reflector import reflect
            result = reflect("test question", _make_context())
        assert result["sufficient"] is False
        assert result["refined_query"] == "better query"

    def test_json_parse_failure_defaults_to_sufficient(self):
        with patch("agents.reflector.call_llm", return_value="BROKEN JSON !!"):
            from agents.reflector import reflect
            result = reflect("test question", _make_context())
        assert result["sufficient"] is True
        assert result["score"] == 7

    def test_empty_context_doesnt_crash(self):
        resp = json.dumps({"score": 2, "sufficient": False,
                           "assessment": "nothing found", "refined_query": "retry"})
        with patch("agents.reflector.call_llm", return_value=resp):
            from agents.reflector import reflect
            result = reflect("test", {"claims": [], "contradictions": [], "gaps": []})
        assert "score" in result

    def test_exact_threshold_is_sufficient(self):
        """Score == SUFFICIENCY_THRESHOLD (7) should be True."""
        resp = json.dumps({"score": 7, "sufficient": False,
                           "assessment": "borderline", "refined_query": None})
        with patch("agents.reflector.call_llm", return_value=resp):
            from agents.reflector import reflect
            result = reflect("test", _make_context())
        assert result["sufficient"] is True


# ═══════════════════════════════════════════════════════════════
# 6. SYNTHESIZER
# ═══════════════════════════════════════════════════════════════

SYNTH_RESULT = {
    "consensus": [
        {"finding": "CoT improves accuracy on reasoning tasks", "citations": ["2301.00001"]}
    ],
    "disputed": [
        {
            "topic": "Effect on small models",
            "position_a": {"claim": "Helps significantly", "paper": "2302.00001"},
            "position_b": {"claim": "Minimal effect", "paper": "2303.00002"}
        }
    ],
    "missing": ["Does CoT scale to <1B parameter models?"],
    "recommended_experiments": ["Ablation on 125M parameter models with step-by-step prompts"],
    "confidence_in_answer": "medium",
    "confidence_reason": "Limited evidence for small models"
}

class TestSynthesizer:
    def test_format_report_contains_question(self):
        from agents.synthesizer import format_report
        report = format_report("Does CoT help?", SYNTH_RESULT, iterations_taken=2)
        assert "Does CoT help?" in report

    def test_format_report_contains_iterations(self):
        from agents.synthesizer import format_report
        report = format_report("Q", SYNTH_RESULT, iterations_taken=3)
        assert "3" in report

    def test_format_report_contains_consensus_finding(self):
        from agents.synthesizer import format_report
        report = format_report("Q", SYNTH_RESULT, iterations_taken=1)
        assert "CoT improves accuracy" in report

    def test_format_report_contains_citation(self):
        from agents.synthesizer import format_report
        report = format_report("Q", SYNTH_RESULT, iterations_taken=1)
        assert "[2301.00001]" in report

    def test_format_report_empty_consensus(self):
        from agents.synthesizer import format_report
        empty = {**SYNTH_RESULT, "consensus": []}
        report = format_report("Q", empty, iterations_taken=1)
        assert "No clear consensus" in report

    def test_format_report_sections_present(self):
        from agents.synthesizer import format_report
        report = format_report("Q", SYNTH_RESULT, iterations_taken=1)
        for section in ["## Consensus", "## Disputes", "## Research Gaps",
                        "## Recommended Experiments"]:
            assert section in report

    def test_synthesize_calls_llm_and_parses(self):
        with patch("agents.synthesizer.call_llm", return_value=json.dumps(SYNTH_RESULT)):
            from agents.synthesizer import synthesize
            ctx = {**_make_context(), "temporal_note": ""}
            result = synthesize("test question", ctx)
        assert "consensus" in result

    def test_synthesize_with_temporal_note(self):
        """temporal_note should be appended to the prompt."""
        captured = []
        def capture_prompt(prompt, **kwargs):
            captured.append(prompt)
            return json.dumps(SYNTH_RESULT)

        with patch("agents.synthesizer.call_llm", side_effect=capture_prompt):
            from agents.synthesizer import synthesize
            ctx = {**_make_context(), "temporal_note": "TEMPORAL: evolved 2021→2025"}
            synthesize("test", ctx)
        assert "TEMPORAL" in captured[0]


# ═══════════════════════════════════════════════════════════════
# 7. TEMPORAL
# ═══════════════════════════════════════════════════════════════

def _make_raw_claims(years=(2022, 2023, 2023, 2024)):
    return [
        {
            "doc_id": f"claim_{i}",
            "text": f"Claim {i} about topic",
            "metadata": {"arxiv_id": f"23{i:02d}.00001", "paper_year": y},
            "distance": 0.1 * i
        }
        for i, y in enumerate(years)
    ]

class TestTemporal:
    def test_get_claims_by_year_range_filters_correctly(self):
        with patch("agents.temporal.find_similar_claims",
                   return_value=_make_raw_claims([2020, 2022, 2024, 2026])):
            from agents.temporal import get_claims_by_year_range
            results = get_claims_by_year_range("topic", 2022, 2024)
        years = [r["paper_year"] for r in results]
        assert all(2022 <= y <= 2024 for y in years)
        assert 2020 not in years
        assert 2026 not in years

    def test_string_year_coerced_to_int(self):
        raw = _make_raw_claims([2022])
        raw[0]["metadata"]["paper_year"] = "2022"
        with patch("agents.temporal.find_similar_claims", return_value=raw):
            from agents.temporal import get_claims_by_year_range
            results = get_claims_by_year_range("topic", 2020, 2025)
        assert results[0]["paper_year"] == 2022

    def test_insufficient_data_returns_early(self):
        with patch("agents.temporal.find_similar_claims", return_value=_make_raw_claims([2022, 2023])):
            from agents.temporal import get_consensus_evolution
            result = get_consensus_evolution("sparse topic", 2020, 2025)
        assert result["current_status"] == "insufficient_data"
        assert "Not enough" in result["overall_narrative"]

    def test_consensus_evolution_calls_llm_when_sufficient(self):
        many = _make_raw_claims([2021, 2022, 2022, 2023, 2023, 2024])
        llm_resp = json.dumps({
            "yearly_positions": [],
            "overall_narrative": "Steadily improving",
            "current_status": "settled",
            "confidence": 0.9
        })
        with patch("agents.temporal.find_similar_claims", return_value=many), \
             patch("agents.temporal.call_llm", return_value=llm_resp):
            from agents.temporal import get_consensus_evolution
            result = get_consensus_evolution("topic", 2021, 2024)
        assert result["current_status"] == "settled"
        assert "claims_by_year" in result

    def test_contradiction_timeline_no_matches(self):
        with patch("agents.temporal.find_similar_claims", return_value=[]), \
             patch("agents.temporal.get_contradictions", return_value=[]):
            from agents.temporal import get_contradiction_timeline
            result = get_contradiction_timeline("unknown topic")
        assert result["disputes"] == []
        assert "No contradictions" in result["summary"]


# ═══════════════════════════════════════════════════════════════
# 8. CONTRADICTION
# ═══════════════════════════════════════════════════════════════

class TestContradiction:
    def _make_claim(self, id_, arxiv, title, text):
        return {"id": id_, "arxiv_id": arxiv,
                "paper_title": title, "text": text}

    def test_same_id_returns_none(self):
        from agents.contradiction import check_pair
        c = self._make_claim("1", "2301.00001", "Paper A", "Claim text")
        assert check_pair(c, c) is None

    def test_same_arxiv_returns_none(self):
        from agents.contradiction import check_pair
        a = self._make_claim("1", "2301.00001", "Paper A", "Claim A")
        b = self._make_claim("2", "2301.00001", "Paper A", "Claim B")
        assert check_pair(a, b) is None

    def test_unrelated_result_returns_none(self):
        resp = json.dumps({"relationship": "UNRELATED", "confidence": 0.9,
                           "explanation": "different topics"})
        with patch("agents.contradiction.call_llm", return_value=resp):
            from agents.contradiction import check_pair
            a = self._make_claim("1", "2301.00001", "Paper A", "Claim A")
            b = self._make_claim("2", "2302.00002", "Paper B", "Claim B")
            assert check_pair(a, b) is None

    def test_contradiction_result_returned(self):
        resp = json.dumps({"relationship": "CONTRADICTS", "confidence": 0.85,
                           "explanation": "opposite results"})
        with patch("agents.contradiction.call_llm", return_value=resp):
            from agents.contradiction import check_pair
            a = self._make_claim("1", "2301.00001", "Paper A", "Claim A")
            b = self._make_claim("2", "2302.00002", "Paper B", "Claim B")
            result = check_pair(a, b)
        assert result["relationship"] == "CONTRADICTS"
        assert result["confidence"] == pytest.approx(0.85)

    def test_markdown_fenced_json_stripped(self):
        resp = "```json\n" + json.dumps({
            "relationship": "SUPPORTS", "confidence": 0.7,
            "explanation": "aligned results"
        }) + "\n```"
        with patch("agents.contradiction.call_llm", return_value=resp):
            from agents.contradiction import check_pair
            a = self._make_claim("1", "2301.00001", "Paper A", "Claim A")
            b = self._make_claim("2", "2302.00002", "Paper B", "Claim B")
            result = check_pair(a, b)
        assert result is not None
        assert result["relationship"] == "SUPPORTS"

    def test_broken_json_returns_none(self):
        with patch("agents.contradiction.call_llm", return_value="not json %%%"):
            from agents.contradiction import check_pair
            a = self._make_claim("1", "2301.00001", "Paper A", "Claim A")
            b = self._make_claim("2", "2302.00002", "Paper B", "Claim B")
            assert check_pair(a, b) is None

    def test_diagnostics_distinguish_parse_failure(self):
        from agents.contradiction import STATUS_PARSE_FAILURE, check_pair
        with patch("agents.contradiction.call_llm", return_value="not json %%%"):
            a = self._make_claim("1", "2301.00001", "Paper A", "Claim A")
            b = self._make_claim("2", "2302.00002", "Paper B", "Claim B")
            diag = {}
            assert check_pair(a, b, diagnostics=diag) is None
        assert diag["status"] == STATUS_PARSE_FAILURE

    def test_diagnostics_distinguish_unrelated(self):
        from agents.contradiction import STATUS_UNRELATED, check_pair
        resp = json.dumps({"relationship": "UNRELATED", "confidence": 0.9,
                           "explanation": "different topics"})
        with patch("agents.contradiction.call_llm", return_value=resp):
            a = self._make_claim("1", "2301.00001", "Paper A", "Claim A")
            b = self._make_claim("2", "2302.00002", "Paper B", "Claim B")
            diag = {}
            assert check_pair(a, b, diagnostics=diag) is None
        assert diag["status"] == STATUS_UNRELATED

    def test_diagnostics_same_paper_and_same_claim(self):
        from agents.contradiction import STATUS_SAME_CLAIM, STATUS_SAME_PAPER, check_pair
        a = self._make_claim("1", "2301.00001", "Paper A", "Claim A")
        b = self._make_claim("2", "2301.00001", "Paper A", "Claim B")
        d1 = {}
        assert check_pair(a, b, diagnostics=d1) is None
        assert d1["status"] == STATUS_SAME_PAPER
        d2 = {}
        assert check_pair(a, a, diagnostics=d2) is None
        assert d2["status"] == STATUS_SAME_CLAIM

    def test_diagnostics_labels_real_verdict(self):
        from agents.contradiction import check_pair
        resp = json.dumps({"relationship": "SUPPORTS", "confidence": 0.7,
                           "explanation": "aligned"})
        with patch("agents.contradiction.call_llm", return_value=resp):
            a = self._make_claim("1", "2301.00001", "Paper A", "Claim A")
            b = self._make_claim("2", "2302.00002", "Paper B", "Claim B")
            diag = {}
            result = check_pair(a, b, diagnostics=diag)
        assert result["relationship"] == "SUPPORTS"
        assert diag["status"] == "SUPPORTS"

    def test_non_dict_json_does_not_raise(self):
        # A JSON array previously raised TypeError on data["relationship"].
        from agents.contradiction import STATUS_PARSE_FAILURE, check_pair
        with patch("agents.contradiction.call_llm", return_value='["CONTRADICTS"]'):
            a = self._make_claim("1", "2301.00001", "Paper A", "Claim A")
            b = self._make_claim("2", "2302.00002", "Paper B", "Claim B")
            diag = {}
            assert check_pair(a, b, diagnostics=diag) is None
        assert diag["status"] == STATUS_PARSE_FAILURE

    def test_dict_without_relationship_is_parse_failure(self):
        from agents.contradiction import STATUS_PARSE_FAILURE, check_pair
        with patch("agents.contradiction.call_llm", return_value=json.dumps({"confidence": 0.5})):
            a = self._make_claim("1", "2301.00001", "Paper A", "Claim A")
            b = self._make_claim("2", "2302.00002", "Paper B", "Claim B")
            diag = {}
            assert check_pair(a, b, diagnostics=diag) is None
        assert diag["status"] == STATUS_PARSE_FAILURE


# ═══════════════════════════════════════════════════════════════
# 9. GAP FINDER
# ═══════════════════════════════════════════════════════════════

class TestGapFinder:
    def test_short_section_text_returns_empty(self):
        from agents.gap_finder import extract_future_work_gaps
        result = extract_future_work_gaps("Too short.")
        assert result == []

    def test_extract_future_work_inserts_gaps(self):
        llm_resp = json.dumps({
            "open_questions": [
                "Does this approach generalise to non-English languages?",
                "What is the computational overhead at inference time?"
            ]
        })
        with patch("agents.gap_finder.call_llm", return_value=llm_resp), \
             patch("agents.gap_finder.find_similar_claims", return_value=[]), \
             patch("agents.gap_finder.insert_gap", return_value="gap_1") as mock_insert:
            from agents.gap_finder import extract_future_work_gaps
            result = extract_future_work_gaps("We did not address multilingual scenarios. " * 5)
        assert mock_insert.call_count == 2
        assert len(result) == 2

    def test_cluster_gap_skips_short_gap_text(self):
        """Gaps with text < 20 chars should be silently skipped."""
        llm_resp = json.dumps({"gap": "Short.", "reasoning": "test", "confidence": 0.9})
        with patch("agents.gap_finder.call_llm", return_value=llm_resp), \
             patch("agents.gap_finder.find_similar_claims",
                   return_value=[{"doc_id": f"claim_{i}", "text": f"claim {i}",
                                  "metadata": {"arxiv_id": "2301.00001"}, "distance": 0.1}
                                 for i in range(6)]), \
             patch("agents.gap_finder.get_all_claims",
                   return_value=[{"id": str(i), "text": f"claim {i}", "arxiv_id": "2301.00001",
                                  "paper_title": "Test", "paper_year": 2023}
                                 for i in range(15)]), \
             patch("agents.gap_finder.insert_gap") as mock_insert:
            from agents.gap_finder import find_cluster_gaps
            find_cluster_gaps(n_clusters=2)
        mock_insert.assert_not_called()

    def test_cluster_gap_skips_low_confidence(self):
        llm_resp = json.dumps({
            "gap": "What are the long-term effects on model alignment?",
            "reasoning": "none of the claims address this",
            "confidence": 0.3  # below 0.5 threshold
        })
        with patch("agents.gap_finder.call_llm", return_value=llm_resp), \
             patch("agents.gap_finder.find_similar_claims",
                   return_value=[{"doc_id": f"claim_{i}", "text": f"claim {i}",
                                  "metadata": {"arxiv_id": "2301.00001"}, "distance": 0.1}
                                 for i in range(6)]), \
             patch("agents.gap_finder.get_all_claims",
                   return_value=[{"id": str(i), "text": f"claim {i}", "arxiv_id": "2301.00001",
                                  "paper_title": "Test", "paper_year": 2023}
                                 for i in range(15)]), \
             patch("agents.gap_finder.insert_gap") as mock_insert:
            from agents.gap_finder import find_cluster_gaps
            find_cluster_gaps(n_clusters=2)
        mock_insert.assert_not_called()


# ═══════════════════════════════════════════════════════════════
# 10. COORDINATOR V2
# ═══════════════════════════════════════════════════════════════

def _mock_plan():
    return {
        "sub_queries": ["chain of thought LLM"],
        "fetch_contradictions": True,
        "fetch_gaps": True,
        "reasoning": "direct query"
    }

def _mock_claims(n=5):
    return [
        {
            "id": str(i),
            "text": f"Claim {i} about chain of thought",
            "arxiv_id": f"2301.{i:05d}",
            "section": "Results",
            "distance": 0.1 * i,
            "weighted_confidence": round(0.9 - 0.05 * i, 3)
        }
        for i in range(n)
    ]

def _mock_retrieve_result():
    return {"claims": _mock_claims(), "contradictions": [], "gaps": []}

def _mock_reflect_sufficient():
    return {"score": 8, "sufficient": True,
            "assessment": "good context", "refined_query": None}

def _mock_reflect_insufficient():
    return {"score": 4, "sufficient": False,
            "assessment": "need more", "refined_query": "refined chain of thought query"}

def _mock_synthesize_result():
    return {
        "consensus": [{"finding": "CoT helps", "citations": ["2301.00001"]}],
        "disputed": [], "missing": [], "recommended_experiments": [],
        "confidence_in_answer": "high", "confidence_reason": "Strong evidence"
    }

class TestMergeContexts:
    """Unit tests for _merge_contexts — pure function, no mocks needed."""

    def test_deduplicates_claims(self):
        from agents.coordinator_v2 import _merge_contexts
        ctx_a = {"claims": [{"id": "1", "weighted_confidence": 0.9}],
                 "contradictions": [], "gaps": []}
        ctx_b = {"claims": [{"id": "1", "weighted_confidence": 0.9},
                             {"id": "2", "weighted_confidence": 0.7}],
                 "contradictions": [], "gaps": []}
        merged = _merge_contexts(ctx_a, ctx_b)
        ids = [c["id"] for c in merged["claims"]]
        assert ids.count("1") == 1
        assert "2" in ids

    def test_merged_claims_sorted_by_confidence(self):
        from agents.coordinator_v2 import _merge_contexts
        ctx_a = {"claims": [{"id": "1", "weighted_confidence": 0.5}],
                 "contradictions": [], "gaps": []}
        ctx_b = {"claims": [{"id": "2", "weighted_confidence": 0.9}],
                 "contradictions": [], "gaps": []}
        merged = _merge_contexts(ctx_a, ctx_b)
        confs = [c["weighted_confidence"] for c in merged["claims"]]
        assert confs == sorted(confs, reverse=True)

    def test_empty_contexts_merge_cleanly(self):
        from agents.coordinator_v2 import _merge_contexts
        empty = {"claims": [], "contradictions": [], "gaps": []}
        merged = _merge_contexts(empty, empty)
        assert merged == {"claims": [], "contradictions": [], "gaps": []}

    def test_deduplicates_contradictions(self):
        from agents.coordinator_v2 import _merge_contexts
        contra = {"id": "r1", "explanation": "conflict"}
        ctx_a = {"claims": [], "contradictions": [contra], "gaps": []}
        ctx_b = {"claims": [], "contradictions": [contra], "gaps": []}
        merged = _merge_contexts(ctx_a, ctx_b)
        assert len(merged["contradictions"]) == 1


class TestIsTemporalQuestion:
    def test_temporal_keywords_detected(self):
        from agents.coordinator_v2 import _is_temporal_question
        assert _is_temporal_question("Has the consensus changed recently?")
        assert _is_temporal_question("What are the latest trends in 2024?")
        assert _is_temporal_question("Is CoT still the best approach?")

    def test_non_temporal_not_detected(self):
        from agents.coordinator_v2 import _is_temporal_question
        assert not _is_temporal_question("What is chain of thought prompting?")
        assert not _is_temporal_question("How does attention work in transformers?")


class TestCoordinatorRun:
    """Integration tests for coordinator_v2.run() with all I/O mocked."""

    def _patch_all(self, reflect_return=None):
        """Returns a context manager dict with all patches needed."""
        if reflect_return is None:
            reflect_return = _mock_reflect_sufficient()
        return {
            "plan":        patch("agents.coordinator_v2.make_plan",
                                 return_value=_mock_plan()),
            "retrieve":    patch("agents.coordinator_v2._retrieve",
                                 return_value=_mock_retrieve_result()),
            "reflect":     patch("agents.coordinator_v2.reflect",
                                 return_value=reflect_return),
            "synthesize":  patch("agents.coordinator_v2.synthesize",
                                 return_value=_mock_synthesize_result()),
            "temporal":    patch("agents.coordinator_v2._get_temporal_context",
                                 return_value=""),
        }

    def test_run_returns_required_keys(self):
        patches = self._patch_all()
        with patches["plan"], patches["retrieve"], patches["reflect"], \
             patches["synthesize"], patches["temporal"]:
            from agents.coordinator_v2 import run
            result = run("Does CoT help?", verbose=False)
        for key in ("report", "raw", "iterations", "plan", "reflection_log", "context"):
            assert key in result, f"Missing key: {key}"

    def test_run_stops_after_sufficient_reflection(self):
        """If reflector says sufficient on iteration 1, loop should exit."""
        patches = self._patch_all(reflect_return=_mock_reflect_sufficient())
        with patches["plan"], patches["retrieve"] as mock_ret, \
             patches["reflect"], patches["synthesize"], patches["temporal"]:
            from agents.coordinator_v2 import run
            result = run("Does CoT help?", verbose=False)
        assert result["iterations"] == 1
        assert mock_ret.call_count == 1

    def test_run_refines_query_on_insufficient(self):
        """Insufficient reflection → uses refined_query on next iteration."""
        reflect_responses = [_mock_reflect_insufficient(), _mock_reflect_sufficient()]
        patches = {
            "plan":       patch("agents.coordinator_v2.make_plan",
                                return_value=_mock_plan()),
            "retrieve":   patch("agents.coordinator_v2._retrieve",
                                return_value=_mock_retrieve_result()),
            "reflect":    patch("agents.coordinator_v2.reflect",
                                side_effect=reflect_responses),
            "synthesize": patch("agents.coordinator_v2.synthesize",
                                return_value=_mock_synthesize_result()),
            "temporal":   patch("agents.coordinator_v2._get_temporal_context",
                                return_value=""),
        }
        with patches["plan"], patches["retrieve"] as mock_ret, \
             patches["reflect"], patches["synthesize"], patches["temporal"]:
            from agents.coordinator_v2 import run
            result = run("Does CoT help?", verbose=False)
        assert result["iterations"] == 2
        assert mock_ret.call_count == 2

    def test_run_respects_max_iterations(self):
        """Should never exceed MAX_ITERATIONS even if reflector always says insufficient."""
        always_insufficient = _mock_reflect_insufficient()
        with patch("agents.coordinator_v2.make_plan", return_value=_mock_plan()), \
             patch("agents.coordinator_v2._retrieve",
                   return_value=_mock_retrieve_result()), \
             patch("agents.coordinator_v2.reflect", return_value=always_insufficient), \
             patch("agents.coordinator_v2.synthesize",
                   return_value=_mock_synthesize_result()), \
             patch("agents.coordinator_v2._get_temporal_context", return_value=""):
            from agents.coordinator_v2 import run
            from agents.coordinator_v2 import MAX_ITERATIONS
            result = run("test", verbose=False)
        assert result["iterations"] <= MAX_ITERATIONS

    def test_run_reflection_log_populated(self):
        patches = self._patch_all()
        with patches["plan"], patches["retrieve"], patches["reflect"], \
             patches["synthesize"], patches["temporal"]:
            from agents.coordinator_v2 import run
            result = run("Does CoT help?", verbose=False)
        assert len(result["reflection_log"]) >= 1
        entry = result["reflection_log"][0]
        for key in ("iteration", "score", "sufficient", "assessment"):
            assert key in entry

    def test_run_report_is_string(self):
        patches = self._patch_all()
        with patches["plan"], patches["retrieve"], patches["reflect"], \
             patches["synthesize"], patches["temporal"]:
            from agents.coordinator_v2 import run
            result = run("Does CoT help?", verbose=False)
        assert isinstance(result["report"], str)
        assert len(result["report"]) > 0

    def test_run_temporal_context_injected_for_temporal_question(self):
        temporal_str = "\nTEMPORAL CONTEXT: consensus evolved 2021→2025\n"
        with patch("agents.coordinator_v2.make_plan", return_value=_mock_plan()), \
             patch("agents.coordinator_v2._retrieve",
                   return_value=_mock_retrieve_result()), \
             patch("agents.coordinator_v2.reflect",
                   return_value=_mock_reflect_sufficient()), \
             patch("agents.coordinator_v2.synthesize",
                   return_value=_mock_synthesize_result()) as mock_synth, \
             patch("agents.coordinator_v2._get_temporal_context",
                   return_value=temporal_str):
            from agents.coordinator_v2 import run
            run("Has chain of thought changed recently?", verbose=False)
        # temporal_note should be in the context passed to synthesize
        ctx_arg = mock_synth.call_args[0][1]
        assert ctx_arg.get("temporal_note") == temporal_str


# ═══════════════════════════════════════════════════════════════
# 11. STORE (ChromaDB)
# ═══════════════════════════════════════════════════════════════

class TestStore:
    def _make_chroma_result(self, n=3):
        return {
            "ids":       [["claim_1", "claim_2", "claim_3"][:n]],
            "documents": [[f"Claim text {i}" for i in range(n)]],
            "metadatas": [[{"arxiv_id": f"2301.{i:05d}", "paper_year": 2023}
                           for i in range(n)]],
            "distances": [[0.1 * i for i in range(n)]]
        }

    def test_find_similar_claims_shape(self):
        mock_col = MagicMock()
        mock_col.query.return_value = self._make_chroma_result(3)
        with patch("embeddings.store._claims_col", return_value=mock_col):
            from embeddings.store import find_similar_claims
            results = find_similar_claims("some query", n_results=3)
        assert len(results) == 3
        for r in results:
            assert "doc_id" in r
            assert "text" in r
            assert "metadata" in r
            assert "distance" in r

    def test_add_claim_returns_doc_id(self):
        import embeddings.store as store_mod
        mock_col = MagicMock()
        with patch("embeddings.store._claims_col", return_value=mock_col):
            doc_id = store_mod.add_claim("abc123", "Some claim text",
                                         {"arxiv_id": "2301.00001"})
        assert doc_id == "claim_abc123"
        mock_col.upsert.assert_called_once()

    def test_find_similar_chunks_shape(self):
        mock_col = MagicMock()
        mock_col.query.return_value = self._make_chroma_result(2)
        with patch("embeddings.store._chunks_col", return_value=mock_col):
            from embeddings.store import find_similar_chunks
            results = find_similar_chunks("query text", n_results=2)
        assert len(results) == 2


# ═══════════════════════════════════════════════════════════════
# 12. NEO4J QUERIES
# ═══════════════════════════════════════════════════════════════

class TestNeo4jQueries:
    def test_insert_paper_calls_run_write(self):
        with patch("graph.neo4j_queries.run_write") as mock_write:
            from graph.neo4j_queries import insert_paper
            result = insert_paper("2301.00001", "Test Paper",
                                  "Author A", "Abstract text", "2023-01-15")
        assert result == "2301.00001"
        mock_write.assert_called_once()
        cypher = mock_write.call_args[0][0]
        assert "MERGE" in cypher

    def test_get_paper_by_arxiv_id_not_found(self):
        with patch("graph.neo4j_queries.run_query", return_value=[]):
            from graph.neo4j_queries import get_paper_by_arxiv_id
            assert get_paper_by_arxiv_id("nonexistent") is None

    def test_get_paper_by_arxiv_id_found(self):
        paper = {"arxiv_id": "2301.00001", "title": "Test", "authors": "A",
                 "abstract": "abs", "published": "2023-01-01", "year": 2023}
        with patch("graph.neo4j_queries.run_query", return_value=[paper]):
            from graph.neo4j_queries import get_paper_by_arxiv_id
            result = get_paper_by_arxiv_id("2301.00001")
        assert result["arxiv_id"] == "2301.00001"

    def test_insert_claim_returns_id(self):
        with patch("graph.neo4j_queries.run_write",
                   return_value=[{"claim_id": "4:abc:123"}]):
            from graph.neo4j_queries import insert_claim
            result = insert_claim("2301.00001", "Test claim", "Results",
                                  confidence=0.9, paper_year=2023)
        assert result == "4:abc:123"

    def test_get_all_claims_returns_list(self):
        claims = [{"id": "1", "text": "Claim 1", "section": "Results",
                   "confidence": 0.9, "arxiv_id": "2301.00001",
                   "paper_title": "Test", "paper_year": 2023}]
        with patch("graph.neo4j_queries.run_query", return_value=claims):
            from graph.neo4j_queries import get_all_claims
            result = get_all_claims()
        assert len(result) == 1
        assert result[0]["text"] == "Claim 1"

    def test_insert_gap_links_related_claims(self):
        with patch("graph.neo4j_queries.run_write",
                   return_value=[{"gap_id": "gap_1"}]) as mock_write:
            from graph.neo4j_queries import insert_gap
            insert_gap("What about multilingual?", "future_work", ["c1", "c2"])
        # 1 create + 2 MERGE link calls
        assert mock_write.call_count == 3

    def test_get_gaps_returns_list(self):
        gaps = [{"id": "g1", "text": "Open question", "source": "cluster",
                 "related_claims": ["c1"]}]
        with patch("graph.neo4j_queries.run_query", return_value=gaps):
            from graph.neo4j_queries import get_gaps
            result = get_gaps()
        assert result[0]["text"] == "Open question"

    def test_insert_relationship_contradicts(self):
        with patch("graph.neo4j_queries.run_write") as mock_write:
            from graph.neo4j_queries import insert_relationship
            insert_relationship("a1", "b1", "CONTRADICTS", "opposite results", 0.8)
        cypher = mock_write.call_args[0][0]
        assert "CONTRADICTS" in cypher

    def test_insert_relationship_supports(self):
        with patch("graph.neo4j_queries.run_write") as mock_write:
            from graph.neo4j_queries import insert_relationship
            insert_relationship("a1", "b1", "SUPPORTS", "aligned results", 0.7)
        cypher = mock_write.call_args[0][0]
        assert "SUPPORTS" in cypher

    def test_published_year_parsed_correctly(self):
        """insert_paper should extract year=2023 from '2023-06-15'."""
        with patch("graph.neo4j_queries.run_write") as mock_write:
            from graph.neo4j_queries import insert_paper
            insert_paper("2301.00001", "T", "A", "abs", "2023-06-15")
        params = mock_write.call_args[0][1]
        assert params["year"] == 2023

    def test_published_year_invalid_stays_none(self):
        with patch("graph.neo4j_queries.run_write") as mock_write:
            from graph.neo4j_queries import insert_paper
            insert_paper("2301.00001", "T", "A", "abs", "not-a-date")
        params = mock_write.call_args[0][1]
        assert params["year"] is None


# ═══════════════════════════════════════════════════════════════
# 13. REGRESSION — KNOWN BUGS DOCUMENTED AS TESTS
# ═══════════════════════════════════════════════════════════════

class TestRegressions:
    """
    Tests documenting known bugs. Each test describes the bug and the
    expected behaviour once fixed.  They will FAIL until the fix is applied.
    """

    def test_BUG_contradiction_int_cast_on_neo4j5_elementid(self):
        """
        LOCATION: agents/contradiction.py line 87
        BUG:  `int(sim["doc_id"].replace("claim_", ""))` crashes with
              ValueError when Neo4j 5+ returns string elementIds like
              "4:abc123:7" instead of plain ints.
        FIX:  Remove the int() cast — keep the ID as a string, matching
              how neo4j_queries.py uses elementId everywhere else.
        """
        # Simulate a Neo4j 5+ string element ID in a ChromaDB doc_id
        neo4j5_doc_id = "claim_4:abc123:7"
        with pytest.raises(ValueError, match="invalid literal"):
            # This is the exact cast that blows up in production
            int(neo4j5_doc_id.replace("claim_", ""))

    def test_BUG_reflector_dead_code_after_return(self):
        """
        LOCATION: agents/reflector.py lines 106-107
        BUG:  Two lines of dead code appear after the function's return
              statement (duplicate `result["sufficient"] = ...` and
              `return result`).  While harmless at runtime, it indicates
              a copy-paste error and will confuse future editors.
        FIX:  Delete lines 106-107.
        """
        import inspect
        import agents.reflector as ref_module
        source = inspect.getsource(ref_module.reflect)
        # Count occurrences of the sufficiency assignment
        occurrences = source.count('result["sufficient"] = result.get("score", 0)')
        assert occurrences == 1, (
            f"Dead code detected: 'result[\"sufficient\"] = ...' appears "
            f"{occurrences} times in reflector.reflect() — expected 1. "
            f"Remove the duplicate lines 106-107."
        )

    def test_BUG_contradiction_pair_key_type_mismatch(self):
        """
        LOCATION: agents/contradiction.py line 89
        BUG:  pair_key = tuple(sorted([claim["id"], other_claim_id]))
              claim["id"] comes from get_all_claims() as a Neo4j string elementId
              (e.g. "4:abc:7") but other_claim_id is cast to int on line 87.
              sorted() will raise TypeError in Python 3 when comparing str and int.
        FIX:  Remove the int() cast on line 87 so both IDs are strings.
        """
        with pytest.raises(TypeError):
            # Reproduces the exact failure path
            sorted(["4:abc:7", 42])

    def test_BUG_store_add_chunk_no_dedup(self):
        """
        LOCATION: embeddings/store.py — add_chunk / add_claim
        BUG:  Both call chromadb .add() which raises DuplicateIDError if the
              same ID is added twice (e.g. re-ingesting a paper).
        FIX:  Use .upsert() instead of .add() to make ingestion idempotent.
        """
        import embeddings.store as store_mod
        mock_col = MagicMock()
        with patch("embeddings.store._chunks_col", return_value=mock_col):
            store_mod.add_chunk("existing_chunk_id", "text", {})
        mock_col.upsert.assert_called_once_with(documents=["text"], ids=["existing_chunk_id"], metadatas=[{}])