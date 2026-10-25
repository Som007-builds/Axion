# agents/temporal.py
"""
Temporal reasoning agent.

Capabilities:
  1. get_claims_by_year_range  — semantic search filtered by year
  2. get_consensus_evolution   — how agreement on a topic changed year by year
  3. get_contradiction_timeline — when disputes appeared and whether they resolved
"""

import json
from collections import defaultdict
from llm import call_llm
from graph.neo4j_queries import get_all_claims, get_contradictions
from embeddings.store import find_similar_claims
from utils.llm_parser import safe_json_parse


# ─────────────────────────────────────────────────────────────
# Capability 1: Year-filtered semantic search
# ─────────────────────────────────────────────────────────────

def get_claims_by_year_range(topic: str, year_start: int,
                              year_end: int, n_results: int = 15) -> list[dict]:
    """
    Semantic search for claims about a topic, filtered to a year range.
    Post-filters ChromaDB results by paper_year metadata.
    paper_year is stored as int after fix_chroma_year_type.py backfill;
    isinstance guard handles any stragglers.
    """
    raw_results = find_similar_claims(topic, n_results=n_results * 3)

    filtered = []
    for r in raw_results:
        year = r["metadata"].get("paper_year", 0)
        # Safety net: convert if a stale string slipped through
        if isinstance(year, str):
            try:
                year = int(year)
            except ValueError:
                year = 0
        if year and year_start <= year <= year_end:
            filtered.append({
                "id": r["doc_id"].replace("claim_", ""),
                "text": r["text"],
                "arxiv_id": r["metadata"].get("arxiv_id", "?"),
                "paper_year": year,
                "distance": r["distance"]
            })

    filtered.sort(key=lambda x: (x["distance"], x["paper_year"]))
    return filtered[:n_results]


# ─────────────────────────────────────────────────────────────
# Capability 2: Consensus evolution
# ─────────────────────────────────────────────────────────────

EVOLUTION_PROMPT = """You are a science historian analyzing how a research field's consensus changed over time.

Topic: "{topic}"

Here are claims about this topic, grouped by year:

{claims_by_year}

For each year that has claims, describe:
- What position the field was taking that year
- Whether it agreed, disagreed, or was uncertain compared to the previous year
- Any notable shift in language or framing

Then write an overall narrative of how consensus evolved from {year_start} to {year_end}.

Return ONLY valid JSON, no other text:
{{
  "yearly_positions": [
    {{
      "year": 2022,
      "position": "one sentence describing what the field believed this year",
      "shift_from_prior": "same | strengthened | weakened | reversed | first_appearance",
      "confidence": 0.7,
      "key_claim_arxiv_ids": ["arxiv_id_1"]
    }}
  ],
  "overall_narrative": "2-3 sentences describing the arc of consensus change",
  "current_status": "settled | active_debate | fragmented | emerging",
  "confidence": 0.0
}}
"""

# `confidence` per year is 0.0-1.0 and reflects how strongly the claims from
# that year support the stated position (how much evidence vs. uncertainty).


def get_consensus_evolution(topic: str, year_start: int = 2020,
                             year_end: int = 2025) -> dict:
    """
    Traces how the field's consensus on a topic evolved year by year.
    """
    claims = get_claims_by_year_range(topic, year_start, year_end, n_results=40)

    if len(claims) < 3:
        return {
            "yearly_positions": [],
            "overall_narrative": (
                f"Not enough claims in the graph about '{topic}' for temporal analysis. "
                f"Ingest more papers from {year_start}-{year_end}."
            ),
            "current_status": "insufficient_data",
            "confidence": 0.0
        }

    by_year = defaultdict(list)
    for c in claims:
        by_year[c["paper_year"]].append(c)

    claims_by_year_text = ""
    for year in sorted(by_year.keys()):
        claims_by_year_text += f"\n{year}:\n"
        for c in by_year[year][:4]:
            claims_by_year_text += f"  [{c['arxiv_id']}] {c['text'][:120]}\n"

    prompt = EVOLUTION_PROMPT.format(
        topic=topic,
        claims_by_year=claims_by_year_text,
        year_start=year_start,
        year_end=year_end
    )

    raw = call_llm(prompt, max_tokens=1500, context="temporal.evolution")

    # Phase 1: safe_json_parse handles all malformed output forms
    result = safe_json_parse(raw, context="temporal.evolution") or {}
    if not isinstance(result, dict):
        result = {}

    result["claims_by_year"] = {
        str(year): claims_list for year, claims_list in by_year.items()
    }

    return result


# ─────────────────────────────────────────────────────────────
# Capability 3: Contradiction timeline
# ─────────────────────────────────────────────────────────────

CONTRADICTION_TIMELINE_PROMPT = """You are analyzing the history of a scientific dispute.

Topic: "{topic}"

Here are contradictions between papers, with the year of each paper's claims:

{contradiction_text}

For each contradiction:
- When did the dispute first appear?
- Is it still active (both positions still defended in recent papers) or resolved?
- If resolved, which position won and when?

Each contradiction below is annotated with the two claim IDs (CLAIM_ID) that clash.
Copy those IDs into `related_claim_ids` for the matching dispute. Never invent IDs.

Return ONLY valid JSON, no other text:
{{
  "disputes": [
    {{
      "description": "what the dispute is about",
      "first_appeared": 2022,
      "status": "active | resolved | fading",
      "resolution": "which position appears to have won, or null if unresolved",
      "resolution_year": null,
      "related_claim_ids": ["CLAIM_ID_A", "CLAIM_ID_B"]
    }}
  ],
  "summary": "one paragraph on the overall dispute landscape for this topic"
}}
"""


def get_contradiction_timeline(topic: str, year_start: int = 2019,
                               year_end: int = 2026) -> dict:
    """
    Finds contradictions related to a topic and analyzes when they appeared
    and whether they have been resolved.
    """
    relevant_claims = get_claims_by_year_range(
        topic, year_start, year_end, n_results=40
    )
    if not relevant_claims:
        return {
            "disputes": [],
            "summary": (
                f"No contradictions or matching claims found for '{topic}' "
                f"in {year_start}-{year_end}. An empty result does not "
                "establish that the topic is undisputed."
            ),
            "candidate_claim_count": 0,
            "contradiction_count": 0,
            "year_start": year_start,
            "year_end": year_end,
        }

    all_contradictions = get_contradictions()

    # Some migrated Chroma records still carry their old SQLite numeric IDs.
    # Resolve them to the current Neo4j element IDs by claim text (and arXiv ID
    # where possible); no fuzzy topic matching is used here.
    all_claims = []
    try:
        all_claims = get_all_claims()
    except Exception:
        all_claims = []

    all_ids = {str(c.get("id")) for c in all_claims if c.get("id") is not None}
    by_text: dict[str, list[str]] = defaultdict(list)
    by_text_arxiv: dict[tuple[str, str], list[str]] = defaultdict(list)
    for c in all_claims:
        cid = str(c.get("id"))
        text_key = " ".join(str(c.get("text", "")).split()).lower()
        if text_key:
            by_text[text_key].append(cid)
            arxiv = str(c.get("arxiv_id") or "").strip()
            if arxiv:
                by_text_arxiv[(text_key, arxiv)].append(cid)

    resolved_ids: set[str] = set()
    for claim in relevant_claims:
        raw_id = str(claim.get("id"))
        if raw_id in all_ids:
            resolved_ids.add(raw_id)
            continue
        text_key = " ".join(str(claim.get("text", "")).split()).lower()
        arxiv = str(claim.get("arxiv_id") or "").strip()
        candidates = by_text_arxiv.get((text_key, arxiv)) if arxiv else None
        if not candidates:
            candidates = by_text.get(text_key)
        if candidates and len(set(candidates)) == 1:
            resolved_ids.add(candidates[0])

    relevant_ids = resolved_ids or {str(c.get("id")) for c in relevant_claims}
    topic_contradictions = [
        c for c in all_contradictions
        if str(c.get("claim_a_id")) in relevant_ids
        or str(c.get("claim_b_id")) in relevant_ids
    ]

    if not topic_contradictions:
        return {
            "disputes": [],
            "summary": (
                f"No contradictions found related to '{topic}' in the current "
                f"graph for publication years {year_start}-{year_end}. This "
                "does not establish that the topic is undisputed."
            ),
            "candidate_claim_count": len(relevant_claims),
            "contradiction_count": 0,
            "year_start": year_start,
            "year_end": year_end,
        }

    year_by_id = {c["id"]: c["paper_year"] for c in relevant_claims}
    for c in all_claims:
        if c["id"] not in year_by_id and c["paper_year"]:
            year_by_id[c["id"]] = c["paper_year"]

    contradiction_text = ""
    claim_text_by_id = {}
    for contra in topic_contradictions[:8]:
        year_a = year_by_id.get(contra.get("claim_a_id"), "unknown")
        year_b = year_by_id.get(contra.get("claim_b_id"), "unknown")
        a_id = contra.get("claim_a_id") or ""
        b_id = contra.get("claim_b_id") or ""
        if a_id:
            claim_text_by_id[a_id] = contra.get("claim_a", "")
        if b_id:
            claim_text_by_id[b_id] = contra.get("claim_b", "")
        contradiction_text += (
            f"\n- [{year_a}] (CLAIM_ID: {a_id}) {contra.get('claim_a', '')[:100]}\n"
            f"  CONTRADICTS\n"
            f"  [{year_b}] (CLAIM_ID: {b_id}) {contra.get('claim_b', '')[:100]}\n"
            f"  Reason: {contra.get('explanation', '')[:80]}\n"
        )

    prompt = CONTRADICTION_TIMELINE_PROMPT.format(
        topic=topic,
        contradiction_text=contradiction_text
    )

    raw = call_llm(prompt, max_tokens=1000, context="temporal.timeline")

    # Phase 1: safe_json_parse
    result = safe_json_parse(raw, context="temporal.timeline") or {}
    if not isinstance(result, dict):
        result = {}

    disputes = result.get("disputes")
    if not isinstance(disputes, list):
        disputes = []
        result["disputes"] = disputes

    # Data-driven fallback: when the model omits first_appeared, use the
    # earliest paper year involved in the matched contradictions.
    known_years = [y for y in year_by_id.values() if isinstance(y, int) and y]
    fallback_year = min(known_years) if known_years else None
    for d in disputes:
        if not isinstance(d, dict):
            continue
        if not isinstance(d.get("first_appeared"), (int, float)) and fallback_year:
            d["first_appeared"] = fallback_year

    # Provide claim-id -> text lookup so the API can render readable
    # key-claim chips without a second graph round trip.
    result["claim_text_by_id"] = claim_text_by_id
    result["candidate_claim_count"] = len(relevant_claims)
    result["contradiction_count"] = len(topic_contradictions)
    result["year_start"] = year_start
    result["year_end"] = year_end
    if not result.get("summary"):
        result["summary"] = (
            f"Compared {len(relevant_claims)} retrieved claims with "
            f"{len(topic_contradictions)} candidate contradiction pairs in the "
            f"{year_start}-{year_end} publication window. The timeline is a "
            "model interpretation of this sample, not a verified history."
        )

    return result