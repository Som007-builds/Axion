# agents/gap_finder.py
"""
Research Gap Finder.

Phase 1: All JSON parsing now uses utils.llm_parser.safe_json_parse().
         Markdown fence stripping removed (handled centrally).

Phase 2: Per-gap and per-cluster fault isolation — one failed gap never
         stops the rest of the extraction run.
"""

import logging
from graph.neo4j_queries import get_all_claims, insert_gap, get_gaps
from embeddings.store import find_similar_claims
from llm import call_llm
from utils.llm_parser import safe_json_parse
from utils.logger import get_logger

logger = get_logger(__name__)


FUTURE_WORK_PROMPT = """You are analyzing the "Future Work" or "Limitations" section of an AI research paper.

Extract the open research questions this paper explicitly says it did NOT answer.
Return each as a standalone research question a future paper could address.

Section text:
---
{text}
---

Return ONLY valid JSON, no other text:
{{
  "open_questions": [
    "A specific research question this paper left unanswered"
  ]
}}
"""

CLUSTER_GAP_PROMPT = """You are analyzing a cluster of related research claims from multiple papers.

These claims all relate to the same topic, but together they reveal what's missing.

Claims:
{claims}

Think carefully: What important question do these claims collectively circle around but none of them directly answer?
The gap should be:
- Specific enough to be a research question
- Not already answered by any of the claims above
- Something the field would care about

Return ONLY valid JSON, no other text:
{{
  "gap": "The specific unanswered research question",
  "reasoning": "Why none of the above claims actually answers this",
  "confidence": 0.0
}}
"""


def _build_claim_index(claims: list[dict]) -> dict:
    """Index Neo4j claims by id and by exact normalised text (+ arXiv id)."""
    by_id = {str(c.get("id")) for c in claims if c.get("id") is not None}
    by_text: dict[str, list[str]] = {}
    by_text_arxiv: dict[tuple[str, str], list[str]] = {}
    for c in claims:
        cid = str(c.get("id"))
        text_key = " ".join(str(c.get("text", "")).split()).lower()
        if not text_key:
            continue
        by_text.setdefault(text_key, []).append(cid)
        arxiv = str(c.get("arxiv_id") or "").strip()
        if arxiv:
            by_text_arxiv.setdefault((text_key, arxiv), []).append(cid)
    return {
        "by_id": by_id,
        "by_text": by_text,
        "by_text_arxiv": by_text_arxiv,
    }


def _resolve_matches(matches: list[dict], index: dict) -> list[str]:
    """Map Chroma matches to current Neo4j claim IDs.

    Chroma records can still carry old SQLite numeric IDs. Resolve only by an
    exact normalised text match (preferring the same arXiv ID); never guess.
    """
    ids: list[str] = []
    seen: set[str] = set()
    by_id = index.get("by_id", set())
    by_text = index.get("by_text", {})
    by_text_arxiv = index.get("by_text_arxiv", {})

    for match in matches:
        raw_id = str(match.get("doc_id", "")).replace("claim_", "").strip()
        candidates: list[str] = []
        if raw_id in by_id:
            candidates = [raw_id]
        else:
            text_key = " ".join(str(match.get("text", "")).split()).lower()
            arxiv = str((match.get("metadata") or {}).get("arxiv_id") or "").strip()
            if arxiv:
                candidates = by_text_arxiv.get((text_key, arxiv), [])
            if not candidates:
                candidates = by_text.get(text_key, [])
        unique = list(dict.fromkeys(candidates))
        if len(unique) == 1 and unique[0] not in seen:
            seen.add(unique[0])
            ids.append(unique[0])
    return ids


def _resolve_similar_claim_ids(query_text: str, n: int = 5,
                               index: dict | None = None) -> list:
    """
    Find n semantically similar claims for a query text.
    Returns a list of current Neo4j element IDs (strings). If the graph cannot
    be read, the raw Chroma IDs are returned as a degraded fallback.
    """
    similar = find_similar_claims(query_text, n_results=n)
    if not similar:
        return []
    if index is None:
        try:
            index = _build_claim_index(get_all_claims())
        except Exception as e:
            logger.warning(f"  [gap_finder] claim ID resolution unavailable: {e}")
            index = {}
    resolved = _resolve_matches(similar, index)
    if resolved:
        return resolved[:n]
    return [
        str(s.get("doc_id", "")).replace("claim_", "")
        for s in similar[:n]
        if s.get("doc_id")
    ]


def extract_future_work_gaps(section_text: str) -> list:
    """
    Mine future work / limitations sections for open questions.
    Each gap is auto-linked to the 5 most semantically similar claims.
    Returns list of gap_ids inserted.
    """
    if len(section_text.strip()) < 50:
        return []

    prompt = FUTURE_WORK_PROMPT.format(text=section_text[:2000])
    raw = call_llm(prompt, max_tokens=800, context="gap_finder.future_work")

    # Phase 1: safe_json_parse — handles markdown fences, partial JSON, etc.
    data = safe_json_parse(raw, context="gap_finder.future_work")

    gap_ids = []
    if not data or not isinstance(data, dict):
        logger.warning("  [gap_finder] future_work: parse returned no usable data.")
        return gap_ids

    for question in data.get("open_questions", []):
        if not isinstance(question, str) or len(question) < 20:
            continue
        # Phase 2: per-gap fault isolation
        try:
            related_claim_ids = _resolve_similar_claim_ids(question, n=5)
            gap_id = insert_gap(
                text=question,
                source="future_work",
                related_claim_ids=related_claim_ids
            )
            gap_ids.append(gap_id)
            logger.info(f"  Gap (future_work, {len(related_claim_ids)} links): {question[:70]}")
        except Exception as e:
            logger.warning(f"  [gap_finder] future_work gap insert failed: {e}")

    return gap_ids


def find_cluster_gaps(n_clusters: int = 10) -> list:
    """
    For a sample of claims, get their semantic neighbors and ask the LLM
    what research question the cluster circles but never directly answers.
    """
    all_claims = get_all_claims()
    if len(all_claims) < 5:
        logger.warning("  Not enough claims in DB. Run ingestion first.")
        return []

    claim_index = _build_claim_index(all_claims)
    step = max(1, len(all_claims) // n_clusters)
    seed_claims = all_claims[::step][:n_clusters]

    gap_ids = []

    for seed in seed_claims:
        neighbors = find_similar_claims(seed["text"], n_results=6)

        if len(neighbors) < 3:
            continue

        claims_text = ""
        cluster_claim_ids = _resolve_matches(neighbors, claim_index)
        for i, n in enumerate(neighbors):
            claims_text += f"{i+1}. [{n['metadata'].get('arxiv_id', '?')}] {n['text']}\n"

        prompt = CLUSTER_GAP_PROMPT.format(claims=claims_text)
        raw = call_llm(prompt, max_tokens=500, context="gap_finder.cluster")

        # Phase 1: safe_json_parse
        data = safe_json_parse(raw, context="gap_finder.cluster")
        if not data or not isinstance(data, dict):
            continue

        gap_text = data.get("gap", "")
        confidence = data.get("confidence", 0)

        if not isinstance(gap_text, str) or len(gap_text) < 20 or confidence < 0.5:
            continue

        # Phase 2: per-cluster fault isolation
        try:
            gap_id = insert_gap(
                text=gap_text,
                source="cluster",
                related_claim_ids=cluster_claim_ids,
                confidence=float(confidence),
            )
            gap_ids.append(gap_id)
            logger.info(f"  Gap (cluster, {len(cluster_claim_ids)} links): {gap_text[:70]}")
        except Exception as e:
            logger.warning(f"  [gap_finder] cluster gap insert failed: {e}")

    return gap_ids


def run_gap_finding():
    """Main entry point for gap finding."""
    total_gaps = 0

    logger.info("Finding cluster gaps...")
    cluster_gap_ids = find_cluster_gaps(n_clusters=10)
    total_gaps += len(cluster_gap_ids)

    logger.info(f"\nTotal gaps found: {total_gaps}")
    return total_gaps


if __name__ == "__main__":
    run_gap_finding()