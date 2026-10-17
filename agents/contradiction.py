# agents/contradiction.py
"""
PHASE 6 CHANGE:
  run_contradiction_detection() now calls recalculate_all() after every
  detection run so claim confidence scores are always up to date after
  new CONTRADICTS/SUPPORTS edges are created.
"""
import json
import logging
from config import CONTRADICTION_MAX_DISTANCE
from graph.neo4j_queries import get_all_claims, insert_relationship, get_contradictions
from embeddings.store import find_similar_claims
from llm import call_llm

logger = logging.getLogger(__name__)


CONTRADICTION_PROMPT = """You are a strict research analyst deciding whether two scientific claims are in direct conflict.

Claim A (from paper: {paper_a}):
"{claim_a}"

Claim B (from paper: {paper_b}):
"{claim_b}"

A CONTRADICTION requires ALL THREE of the following to hold clearly:
  1. SAME PHENOMENON — both claims concern the same intervention or variable
     acting on the same outcome.
  2. COMPARABLE MEASUREMENT — both report the same metric or evaluation setup.
  3. OPPOSITE OUTCOME — one asserts a benefit/higher result where the other
     asserts no effect or a harmful/lower result.

If any of the three does not clearly hold, the claims are NOT contradictory.
Specifically, none of the following is a contradiction on its own:
  - different numbers, datasets, model sizes, or experimental setups
  - different metrics or evaluation protocols
  - a merely loose topical overlap, or the absence of agreement
  - one claim being broader or more specific than the other

Claims that both report a positive effect SUPPORT each other. Claims about
different phenomena, or with no logical interaction, are UNRELATED.

Worked example — this IS a contradiction:
  Claim A: "Retrieval augmentation improves factual accuracy on open-domain QA."
  Claim B: "Retrieval augmentation degrades factual accuracy on open-domain QA."
  Same intervention, same measured quantity, opposite directions, so all three
  booleans are true and the relationship is CONTRADICTS. A different dataset or
  model size would not change that: what matters is the quantity being measured
  and the direction claimed, not the exact experiment.

Be conservative: when the relationship is arguable, answer UNRELATED.

Return ONLY valid JSON, no other text:
{{
  "same_phenomenon": false,
  "comparable_measurement": false,
  "opposite_outcome": false,
  "relationship": "CONTRADICTS or SUPPORTS or UNRELATED",
  "confidence": 0.0,
  "explanation": "one sentence explaining your judgment"
}}

Set "relationship" to CONTRADICTS only when all three booleans are true.
"""


# Statuses reported through the optional ``diagnostics`` out-param of
# ``check_pair``. Without them, SAME_CLAIM, SAME_PAPER, UNRELATED and a JSON
# parse failure all collapse to ``None`` — which made it impossible to tell a
# model failure apart from a genuine "no relationship" verdict during eval.
STATUS_SAME_CLAIM = "SAME_CLAIM"
STATUS_SAME_PAPER = "SAME_PAPER"
STATUS_UNRELATED = "UNRELATED"
STATUS_PARSE_FAILURE = "PARSE_FAILURE"
# The model said CONTRADICTS but failed to justify it with the required
# decomposition (same phenomenon + comparable measurement + opposite outcome).
# Recorded separately so the eval harness can see over-calling being corrected.
STATUS_DEMOTED = "DEMOTED_BY_DECOMPOSITION"

# The three booleans the model must set for a CONTRADICTS verdict to count.
DECOMPOSITION_KEYS = ("same_phenomenon", "comparable_measurement", "opposite_outcome")


def _as_bool(value) -> bool:
    """Tolerant boolean coercion for LLM JSON (True/"true"/"yes"/1 → True)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1")
    return False


def _parse_json_object(raw: str) -> dict | None:
    """Best-effort extraction of a JSON object from a raw LLM response.

    Tolerates markdown fences and leading/trailing prose. Returns ``None``
    (never raises) when no usable object is present.
    """
    if not raw:
        return None

    # Strip markdown fences if present
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    candidates = [raw]
    start = raw.find("{")
    if start > 0:
        candidates.append(raw[start:])

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def check_pair(claim_a: dict, claim_b: dict, diagnostics: dict | None = None) -> dict | None:
    """Classify the relationship between two claims.

    Returns the parsed verdict dict for CONTRADICTS/SUPPORTS and ``None`` for
    every other outcome. When ``diagnostics`` is passed, ``diagnostics["status"]``
    is set to one of ``SAME_CLAIM``, ``SAME_PAPER``, ``UNRELATED``,
    ``PARSE_FAILURE`` or the relationship label — so callers (notably the eval
    harness) can distinguish a JSON parse failure from a genuine UNRELATED
    verdict.
    """
    def _mark(status: str, data: dict | None = None) -> None:
        if diagnostics is None:
            return
        diagnostics["status"] = status
        if data is not None:
            # Keep the decomposition visible for UNRELATED/demoted verdicts so
            # over- and under-calling can be told apart during evaluation.
            diagnostics["flags"] = {
                key: _as_bool(data.get(key)) for key in DECOMPOSITION_KEYS
            }

    id_a = str(claim_a.get("id", "") or "").strip()
    id_b = str(claim_b.get("id", "") or "").strip()
    if id_a and id_a == id_b:
        _mark(STATUS_SAME_CLAIM)
        return None

    arxiv_a = str(claim_a.get("arxiv_id", "") or "").strip()
    arxiv_b = str(claim_b.get("arxiv_id", "") or "").strip()
    # Only a *shared, known* paper qualifies: two claims whose arxiv id is
    # missing are not from the same paper merely because both are empty.
    if arxiv_a and arxiv_a == arxiv_b:
        _mark(STATUS_SAME_PAPER)
        return None

    prompt = CONTRADICTION_PROMPT.format(
        claim_a=claim_a["text"],
        paper_a=claim_a["paper_title"],
        claim_b=claim_b["text"],
        paper_b=claim_b["paper_title"],
    )

    raw = call_llm(prompt, max_tokens=1024)

    data = _parse_json_object(raw)
    if not isinstance(data, dict) or "relationship" not in data:
        _mark(STATUS_PARSE_FAILURE)
        return None

    relationship = str(data["relationship"]).strip().upper()
    if relationship == STATUS_UNRELATED:
        # Record the decomposition too: when a known contradiction is judged
        # UNRELATED this is the only way to see which criterion failed.
        _mark(STATUS_UNRELATED, data)
        return None

    # Deterministic guard: a CONTRADICTS verdict only counts when the model
    # actually justified it with all three decomposition booleans. Without this
    # the model over-calls CONTRADICTS at high confidence (96 of the 224
    # production edges carried confidence 1.0 while only 4 survived audit).
    if relationship == "CONTRADICTS" and not all(
        _as_bool(data.get(key)) for key in DECOMPOSITION_KEYS
    ):
        _mark(STATUS_DEMOTED, data)
        return None

    _mark(relationship, data)
    return data


def run_contradiction_detection(limit_to_claim_ids: list[str] = None) -> int:
    all_claims = get_all_claims()
    
    if limit_to_claim_ids is not None:
        limit_set = set(str(cid) for cid in limit_to_claim_ids)
        target_claims = [c for c in all_claims if str(c["id"]) in limit_set]
        logger.info(f"Running contradiction detection on {len(target_claims)} target claims (out of {len(all_claims)} total)...")
    else:
        target_claims = all_claims
        logger.info(f"Running contradiction detection on all {len(all_claims)} claims...")

    relationships_found = 0
    pairs_checked = set()

    for claim in target_claims:
        similar = find_similar_claims(claim["text"], n_results=8)

        for sim in similar:
            # Neo4j 5+ returns string elementIds — do NOT cast to int
            other_claim_id = sim["doc_id"].replace("claim_", "")

            # The vector search can return the claim's own embedding; skip it
            # rather than burning an iteration on a guaranteed no-op.
            if other_claim_id == str(claim["id"]):
                continue

            # Both ids are strings — sorted() is safe
            pair_key = tuple(sorted([str(claim["id"]), other_claim_id]))
            if pair_key in pairs_checked:
                continue
            pairs_checked.add(pair_key)

            if sim["distance"] > CONTRADICTION_MAX_DISTANCE:
                continue

            other_claims = [c for c in all_claims if str(c["id"]) == other_claim_id]
            if not other_claims:
                continue
            other_claim = other_claims[0]

            result = check_pair(claim, other_claim)
            if result is None:
                continue

            insert_relationship(
                claim_a_id=claim["id"],
                claim_b_id=other_claim_id,
                rel_type=result["relationship"],
                explanation=result["explanation"],
                confidence=result["confidence"],
            )

            relationships_found += 1

            if result["relationship"] == "CONTRADICTS":
                logger.info(
                    f"\n  CONTRADICTION (confidence: {result['confidence']:.2f})\n"
                    f"  A: {claim['text'][:80]}\n"
                    f"  B: {other_claim['text'][:80]}\n"
                    f"  Reason: {result['explanation']}"
                )

    logger.info(f"\nDone. Found {relationships_found} relationships.")

    # Phase 6: recalculate confidence scores now that new edges exist
    logger.info("\nRecalculating claim confidence scores...")
    try:
        from agents.confidence_updater import recalculate_all
        summary = recalculate_all()
        logger.info(
            f"  Updated {summary['total_updated']} claims: "
            f"{summary['boosted']} boosted, "
            f"{summary['penalized']} penalized, "
            f"{summary['unchanged']} unchanged"
        )
        if summary.get("most_penalized"):
            mp = summary["most_penalized"]
            logger.info(f"  Most penalized: {mp['text'][:60]}... "
                        f"({mp['base']:.2f} → {mp['new']:.2f})")
    except Exception as e:
        logger.warning(f"  Warning: confidence recalculation failed — {e}")

    return relationships_found


if __name__ == "__main__":
    run_contradiction_detection()