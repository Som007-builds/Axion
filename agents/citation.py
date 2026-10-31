# agents/citation.py
"""
Citation engine — fetches and applies citation counts from Semantic Scholar.

API docs: https://api.semanticscholar.org
- Free, no key required for up to 100 requests / 5 minutes
- Returns citationCount for any paper by ArXiv ID

Usage:
    python main.py --mode citations
"""
import time
import math
import logging
import requests
from graph.neo4j_client import run_query, run_write

logger = logging.getLogger(__name__)

SEMANTIC_SCHOLAR_BASE = "https://api.semanticscholar.org/graph/v1/paper"
REQUEST_DELAY = 1.5     # seconds between requests — stay under rate limit
_CACHE: dict[str, int] = {}   # arxiv_id → citation_count (process lifetime)


# ─── Fetch ────────────────────────────────────────────────────

def fetch_citation_count(arxiv_id: str) -> int | None:
    """
    Fetch citation count for a paper from Semantic Scholar.
    Returns None if the request fails (caller decides how to handle).
    Returns 0 if the paper isn't indexed.
    Uses in-process cache to avoid duplicate requests.
    """
    if arxiv_id in _CACHE:
        return _CACHE[arxiv_id]

    url = f"{SEMANTIC_SCHOLAR_BASE}/arXiv:{arxiv_id}"
    params = {"fields": "citationCount,title"}

    try:
        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 404:
            _CACHE[arxiv_id] = 0
            return 0

        if response.status_code == 429:
            logger.warning(f"  [Citation] Rate limited. Waiting 30s before retry...")
            time.sleep(30)
            return fetch_citation_count(arxiv_id)   # single retry

        response.raise_for_status()
        data = response.json()
        count = data.get("citationCount") or 0
        _CACHE[arxiv_id] = count
        return count

    except requests.RequestException as e:
        logger.error(f"  [Citation] Request failed for {arxiv_id}: {e}")
        return None


# ─── Store ────────────────────────────────────────────────────

def update_paper_citation_count(arxiv_id: str) -> int | None:
    """
    Fetch and persist citation count for one paper in Neo4j.
    Returns the count, or None if the fetch failed.
    """
    count = fetch_citation_count(arxiv_id)
    if count is None:
        return None

    run_write("""
        MATCH (p:Paper {arxiv_id: $arxiv_id})
        SET p.citation_count = $count,
            p.citations_updated_at = datetime()
    """, {"arxiv_id": arxiv_id, "count": count})

    return count


def update_all_citation_counts(delay: float = REQUEST_DELAY):
    """
    Fetch citation counts for all papers in the graph that have never been
    fetched or haven't been refreshed in 7 days.
    """
    papers = run_query("""
        MATCH (p:Paper)
        WHERE p.citations_updated_at IS NULL
           OR p.citations_updated_at < datetime() - duration('P7D')
        RETURN p.arxiv_id AS arxiv_id, p.title AS title
        ORDER BY p.arxiv_id
    """)

    logger.info(f"Updating citation counts for {len(papers)} papers...")
    updated = 0

    for paper in papers:
        arxiv_id = paper["arxiv_id"]
        count = update_paper_citation_count(arxiv_id)
        if count is not None:
            updated += 1
            logger.info(f"  [{count:>6}] {(paper['title'] or arxiv_id)[:60]}")
        time.sleep(delay)

    logger.info(f"Done. Updated {updated}/{len(papers)} papers.")


# ─── Weighting ────────────────────────────────────────────────

def get_weighted_confidence(claim_id: str, base_confidence: float) -> float:
    """
    Returns a weighted confidence score adjusted by the source paper's
    citation count.

    Formula:
        boost  = log2(2 + citation_count)
        norm   = boost / log2(2 + 10_000)   # ceiling normaliser
        result = base_confidence * (0.5 + 0.5 * norm)

    Properties:
        0 citations  → 0.5 * base_confidence  (slight penalty for uncited)
        100 cites    → ~0.77 * base_confidence
        1 000 cites  → ~0.88 * base_confidence
        10 000 cites → base_confidence        (full score at ceiling)

    Clamped to [0.0, 1.0]. This is a heuristic — say so in demos.
    """
    result = run_query("""
        MATCH (c:Claim) WHERE elementId(c) = $claim_id
        MATCH (c)-[:EXTRACTED_FROM]->(p:Paper)
        RETURN coalesce(p.citation_count, 0) AS citation_count
    """, {"claim_id": str(claim_id)})

    if not result:
        return base_confidence

    citation_count = result[0]["citation_count"] or 0
    MAX_BOOST = math.log2(2 + 10_000)
    boost = math.log2(2 + citation_count)
    normalized = boost / MAX_BOOST
    weighted = base_confidence * (0.5 + 0.5 * normalized)
    return round(min(1.0, max(0.0, weighted)), 4)


# ─── Read helper ──────────────────────────────────────────────

def get_papers_with_citations() -> list[dict]:
    """
    Returns all papers with citation counts, sorted descending.
    """
    return run_query("""
        MATCH (p:Paper)
        RETURN p.arxiv_id AS arxiv_id,
               p.title AS title,
               coalesce(p.citation_count, -1) AS citation_count,
               p.published AS published
        ORDER BY citation_count DESC
    """)