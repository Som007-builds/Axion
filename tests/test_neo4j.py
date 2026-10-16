# tests/test_neo4j.py
"""
Integration tests for the Neo4j graph layer.
Run with: pytest tests/test_neo4j.py -v
Requires a live Neo4j connection.
"""
import pytest
from graph.neo4j_client import run_query
from graph.neo4j_queries import get_all_claims, get_contradictions, get_gaps


pytestmark = pytest.mark.integration


def test_neo4j_connection():
    result = run_query("RETURN 1 AS n")
    assert result[0]["n"] == 1


def test_get_all_claims_returns_list():
    claims = get_all_claims()
    assert isinstance(claims, list)
    if claims:
        assert "text" in claims[0]
        assert "arxiv_id" in claims[0]
        assert "paper_year" in claims[0]
        assert isinstance(claims[0]["paper_year"], (int, type(None)))


def test_get_contradictions_structure():
    contras = get_contradictions()
    assert isinstance(contras, list)
    if contras:
        c = contras[0]
        assert "claim_a_id" in c
        assert "claim_b_id" in c
        assert "explanation" in c
        assert "confidence" in c
        assert isinstance(c["confidence"], float)


def test_get_gaps_all_have_related_claims():
    """
    After fix_empty_gap_links.py, every gap must have at least one RELATED_TO edge.
    If this fails, run: python graph/fix_empty_gap_links.py
    """
    gaps = get_gaps()
    assert isinstance(gaps, list)
    for g in gaps:
        assert "text" in g
        assert "related_claims" in g
        assert len(g["related_claims"]) > 0, (
            f"Gap has no related claims (run fix_empty_gap_links.py): {g['text'][:60]}"
        )


def test_paper_year_is_int():
    """
    After fix_chroma_year_type.py, all paper_year values in Neo4j must be int.
    This checks the Neo4j side; ChromaDB is checked separately.
    """
    claims = get_all_claims()
    for c in claims:
        year = c.get("paper_year")
        if year is not None:
            assert isinstance(year, int), (
                f"paper_year should be int, got {type(year)}: {year}"
            )