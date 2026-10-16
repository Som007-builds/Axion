"""
Year-range claim retrieval — integration test.

This file used to be a script with a `main()` function, which meant pytest
collected **0 tests** from it (a silent no-op). It is now a real pytest test
that exercises `get_claims_in_year_range` against a live Neo4j instance.

Run:  pytest -m integration tests/test_phase4.py
"""
import pytest

pytestmark = pytest.mark.integration


def test_claims_in_year_range_are_within_bounds():
    from graph.neo4j_queries import get_claims_in_year_range

    results = get_claims_in_year_range(2022, 2024)
    assert isinstance(results, list)

    for r in results:
        year = r.get("paper_year")
        assert year is not None, f"claim is missing paper_year: {r}"
        assert 2022 <= year <= 2024, f"Year out of range: {year}"
