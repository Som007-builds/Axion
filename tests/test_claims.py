# tests/test_claims.py
"""
Integration test for the Neo4j claim layer.

Requires a live Neo4j instance (deselected by default via the `integration`
marker). Run explicitly with:

    pytest tests/test_claims.py -v -m integration
"""
import pytest

from graph.neo4j_queries import get_all_claims


@pytest.mark.integration
def test_all_claims_load():
    claims = get_all_claims()
    assert isinstance(claims, list)
    if claims:
        first = claims[0]
        assert "text" in first
        assert "arxiv_id" in first


if __name__ == "__main__":  # pragma: no cover - manual debug aid
    claims = get_all_claims()
    print(f"Total claims: {len(claims)}")
    print()
    for c in claims[:5]:
        print(f"[{c['arxiv_id']}] {c['text'][:100]}")
        print()
