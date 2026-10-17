"""Measure how selective the contradiction retrieval gate is.

The LLM judge is only ever asked about pairs that pass the distance gate in
`agents/contradiction.py`, so the gate decides how many pairs get judged at all
(and therefore how much false-positive noise the judge can produce). This script
replays the *exact* production retrieval path against the live ChromaDB index:

    for each claim: top-8 neighbours by cosine distance, dedup pairs, skip self

and reports the distance distribution plus, for a range of gate values, how many
unique pairs would be sent to the LLM.

Offline and deterministic: no LLM calls, no writes.

    python eval/measure_gate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import CONTRADICTION_MAX_DISTANCE  # noqa: E402
from embeddings.store import _claims_col  # noqa: E402

NEIGHBOURS = 8          # matches find_similar_claims(..., n_results=8)
BATCH = 256             # query_embeddings batch size
GATES = [0.95, 0.50, 0.40, 0.35, 0.30, 0.25, 0.20]
LEGACY_THRESHOLD = 0.95  # the value this replaced


def percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return float("nan")
    idx = min(len(sorted_values) - 1, int(round(pct / 100.0 * (len(sorted_values) - 1))))
    return sorted_values[idx]


def main() -> int:
    try:
        col = _claims_col()
    except Exception as exc:  # noqa: BLE001
        print(f"Could not open the claim collection: {exc}")
        print("Is ChromaDB initialised at data/chroma (run an ingestion first)?")
        return 1

    data = col.get(include=["embeddings"], limit=200_000)
    ids = data["ids"]
    embeddings = data["embeddings"]
    if not ids:
        print("The claim collection is empty.")
        return 1
    if embeddings is None or len(embeddings) == 0:
        print("No embeddings stored in the claim collection.")
        return 1

    print(f"claims in index: {len(ids)}")
    print(f"replaying top-{NEIGHBOURS} retrieval for each claim…")

    # pair_key -> best (smallest) distance seen for that pair
    pair_distance: dict[tuple[str, str], float] = {}
    nearest_non_self: list[float] = []

    for start in range(0, len(ids), BATCH):
        chunk_ids = ids[start:start + BATCH]
        chunk_emb = embeddings[start:start + BATCH]
        res = col.query(
            query_embeddings=chunk_emb,
            n_results=NEIGHBOURS,
            include=["distances"],
        )
        # Row i of the result corresponds to query embedding i.
        for self_id, row_ids, row_dist in zip(chunk_ids, res["ids"], res["distances"]):
            for cand_id, dist in zip(row_ids, row_dist):
                if cand_id == self_id:
                    continue  # the vector search returns the claim itself
                pair = tuple(sorted([self_id, cand_id]))
                prev = pair_distance.get(pair)
                if prev is None or dist < prev:
                    pair_distance[pair] = float(dist)
                if prev is None:
                    nearest_non_self.append(float(dist))

    distances = sorted(pair_distance.values())
    print(f"unique neighbour pairs: {len(distances)}")
    print(
        "distance distribution (asymmetric cosine distance):\n"
        f"  min {distances[0]:.4f}   p50 {percentile(distances, 50):.4f}   "
        f"p90 {percentile(distances, 90):.4f}   p99 {percentile(distances, 99):.4f}   "
        f"max {distances[-1]:.4f}"
    )

    print("\nhow many pairs the LLM judge would see, per gate value:")
    print(f"  {'gate':<8}{'pairs judged':<15}{'% of candidate pairs':<24}claims kept")
    total = len(distances)
    for gate in GATES:
        passing = [d for d in distances if d <= gate]
        kept_claims = len({a for (a, b), d in pair_distance.items() if d <= gate} |
                          {b for (a, b), d in pair_distance.items() if d <= gate})
        share = 100.0 * len(passing) / total if total else 0.0
        kept_share = 100.0 * kept_claims / len(ids)
        tag = ""
        if abs(gate - LEGACY_THRESHOLD) < 1e-9:
            tag = "  <- replaced value"
        if abs(gate - CONTRADICTION_MAX_DISTANCE) < 1e-9:
            tag = "  <- current setting"
        print(
            f"  {gate:<8.2f}{len(passing):<15}{share:<24.1f}{kept_share:.1f}%{tag}"
        )

    legacy_pairs = sum(1 for d in distances if d <= LEGACY_THRESHOLD)
    current_pairs = sum(1 for d in distances if d <= CONTRADICTION_MAX_DISTANCE)
    print(
        f"\nWith the old gate ({LEGACY_THRESHOLD}) {legacy_pairs}/{total} pairs passed, "
        f"i.e. {100.0 * legacy_pairs / total:.1f}% of all retrieved pairs.\n"
        f"With the current gate ({CONTRADICTION_MAX_DISTANCE}) "
        f"{current_pairs}/{total} pairs pass ({100.0 * current_pairs / total:.1f}%), "
        f"cutting judge calls by {100.0 * (1 - current_pairs / max(legacy_pairs, 1)):.1f}%."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
