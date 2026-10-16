"""
Phase 5 regression checks.

Historically this was a script-style smoke test (`python tests/test_phase5.py`)
that pytest collected as **0 tests**. It is now a real pytest module:

* Offline checks (source scans, config, mocked planner, citation formula) run
  by default.
* Checks that touch live Neo4j / ChromaDB / the scheduler are marked
  `integration` and excluded unless you run `pytest -m integration`.

Run:  pytest tests/test_phase5.py                 # offline only
      pytest -m integration tests/test_phase5.py  # + live services
"""
import json
import math
import os
from unittest.mock import patch

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Markers that indicate the retired v1 coordinator is still imported somewhere.
V1_MARKERS = [
    "from agents.coordinator import",
    "from graph.queries import",
    "from graph.schema import",
    "run_v1(",
    "format_v1(",
    "args.v1",
    '"--v1"',
]

# Directories that legitimately hold legacy code, tests, or third-party deps.
_SKIP_DIRS = {
    "archive",
    "venv",
    ".venv",
    "__pycache__",
    ".git",
    "tests",
    "node_modules",
    ".next",
}


def _iter_source_files(root):
    """Yield every .py file under root, pruning vendored/legacy/test dirs."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fname in filenames:
            if fname.endswith(".py"):
                yield os.path.join(dirpath, fname)


# ── A1: v1 coordinator fully removed ─────────────────────────────────
def test_no_v1_imports_outside_archive():
    leaks = []
    for fpath in _iter_source_files(ROOT):
        with open(fpath, encoding="utf-8", errors="ignore") as f:
            text = f.read()
        for marker in V1_MARKERS:
            if marker in text:
                leaks.append(f"{fpath}: {marker!r}")
    assert leaks == [], "v1 coordinator still referenced:\n" + "\n".join(leaks)


def test_main_cli_has_expected_modes_and_no_v1_flag():
    with open(os.path.join(ROOT, "main.py"), encoding="utf-8") as f:
        text = f.read()
    for mode in ("backup", "schedule", "citations"):
        assert f'"{mode}"' in text, f"main.py is missing the {mode!r} mode"
    assert "--v1" not in text, "main.py still exposes the retired --v1 flag"


# ── A2: gap_finder links gaps to real claims ─────────────────────────
def test_gap_finder_links_related_claims():
    with open(os.path.join(ROOT, "agents", "gap_finder.py"), encoding="utf-8") as f:
        text = f.read()
    assert "find_similar_claims" in text
    assert "related_claim_ids" in text
    assert "related_claim_ids=[]" not in text, "gap_finder still writes empty link lists"


# ── A4: planner clamps malformed sub_queries (LLM mocked) ────────────
def test_planner_clamps_dict_sub_queries_and_warns():
    import agents.planner as planner_module

    malformed = {
        "sub_queries": [{"query": "What is CoT?"}],
        "fetch_contradictions": True,
        "fetch_gaps": True,
        "reasoning": "test",
    }
    warnings: list[str] = []

    def _capture(msg, *args, **kwargs):
        warnings.append(msg % args if args else msg)

    with patch.object(planner_module.logger, "warning", side_effect=_capture), patch.object(
        planner_module, "call_llm", return_value=json.dumps(malformed)
    ):
        plan = planner_module.make_plan("test question")

    assert all(isinstance(q, str) for q in plan["sub_queries"])
    assert len(plan["sub_queries"]) <= 3
    combined = "\n".join(warnings)
    assert "⚠️" in combined or "clamped" in combined.lower()


def test_planner_falls_back_on_unparseable_json():
    import agents.planner as planner_module

    with patch.object(planner_module, "call_llm", return_value="not json at all"):
        plan = planner_module.make_plan("what is X?")

    assert plan["sub_queries"] == ["what is X?"]
    assert isinstance(plan["fetch_contradictions"], bool)
    assert isinstance(plan["fetch_gaps"], bool)


# ── A5: backup module + config ───────────────────────────────────────
def test_backup_module_imports_and_lists():
    from graph.backup import create_backup, list_backups, prune_old_backups  # noqa: F401

    assert isinstance(list_backups(), list)


def test_config_exposes_container_name():
    from config import NEO4J_CONTAINER_NAME

    assert NEO4J_CONTAINER_NAME


def test_config_exposes_scheduler_settings():
    from config import (
        SCHEDULER_INTERVAL_HOURS,
        SCHEDULER_PAPERS_PER_RUN,
        SCHEDULER_TOPICS,
    )

    assert isinstance(SCHEDULER_INTERVAL_HOURS, int)
    assert isinstance(SCHEDULER_PAPERS_PER_RUN, int)
    assert isinstance(SCHEDULER_TOPICS, list) and SCHEDULER_TOPICS


# ── B2: citation weighting formula (pure, offline) ───────────────────
def test_citation_weight_formula_is_monotonic_and_clamped():
    def formula(base: float, citations: int) -> float:
        max_boost = math.log2(2 + 10_000)
        boost = math.log2(2 + citations)
        return round(min(1.0, max(0.0, base * (0.5 + 0.5 * boost / max_boost))), 4)

    s0, s100, s8000 = formula(0.9, 0), formula(0.9, 100), formula(0.9, 8000)
    assert 0.0 < s0 < s100 < s8000 <= 1.0


# ── Live-service checks (opt-in: `pytest -m integration`) ────────────
@pytest.mark.integration
def test_every_gap_has_a_related_to_edge():
    from graph.neo4j_client import run_query

    rows = run_query(
        "MATCH (g:Gap) WHERE NOT (g)-[:RELATED_TO]->() RETURN count(g) AS n"
    )
    n_unlinked = rows[0]["n"] if rows else 0
    assert n_unlinked == 0, (
        f"{n_unlinked} gaps have no RELATED_TO edge — run: python -m graph.fix_empty_gap_links"
    )


@pytest.mark.integration
def test_chroma_paper_year_is_int():
    import chromadb

    from config import CHROMA_DIR

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    col = client.get_collection("claims")
    metadatas = col.get(include=["metadatas"]).get("metadatas", [])

    string_years = [
        m.get("paper_year") for m in metadatas if isinstance(m.get("paper_year"), str)
    ]
    assert string_years == [], (
        f"{len(string_years)} paper_year values stored as string — "
        "run: python -m graph.fix_chroma_year_type"
    )


@pytest.mark.integration
def test_neo4j_query_layer_shapes():
    from graph.neo4j_queries import get_all_claims, get_contradictions, get_gaps

    claims = get_all_claims()
    assert isinstance(claims, list)
    if claims:
        c = claims[0]
        assert "text" in c
        assert "arxiv_id" in c
        assert isinstance(c.get("paper_year"), (int, type(None)))

    contras = get_contradictions()
    assert isinstance(contras, list)
    if contras:
        ct = contras[0]
        assert "claim_a_id" in ct
        assert "claim_b_id" in ct
        assert isinstance(ct.get("confidence"), (int, float))

    gaps = get_gaps()
    assert isinstance(gaps, list)
    if gaps:
        assert len(gaps[0].get("related_claims", [])) > 0


@pytest.mark.integration
def test_citation_papers_list():
    from agents.citation import get_papers_with_citations

    assert isinstance(get_papers_with_citations(), list)


@pytest.mark.integration
def test_scheduler_start_is_idempotent_and_stops():
    from ingestion.scheduler import get_run_log, start_scheduler, stop_scheduler

    assert isinstance(get_run_log(), list)

    s = start_scheduler()
    assert s is not None and s.running
    assert start_scheduler() is s  # idempotent — no duplicate scheduler
    stop_scheduler()
    assert not s.running
