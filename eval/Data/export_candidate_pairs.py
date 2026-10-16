"""
Export top-8 semantic claim-neighbor pairs for manual labeling.

This is a one-off data export script. It intentionally reuses the same
find_similar_claims() path as agents/contradiction.py so candidate selection
matches contradiction detection.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from embeddings.store import _claims_col, find_similar_claims
from graph.neo4j_queries import get_all_claims


N_NEIGHBORS = 8
OUT_PATH = Path(__file__).with_name("candidate_pairs.csv")


def _claim_doc_id(claim_id: str) -> str:
    return f"claim_{claim_id}"


def _load_embeddings(doc_ids: list[str]) -> dict[str, list[float]]:
    """Load all stored claim embeddings through the shared Chroma wrapper."""
    if not doc_ids:
        return {}

    results = _claims_col().get(ids=doc_ids, include=["embeddings"])
    ids = results.get("ids") or []
    embeddings = results.get("embeddings")
    if embeddings is None:
        embeddings = []

    return {
        doc_id: embedding.tolist() if hasattr(embedding, "tolist") else embedding
        for doc_id, embedding in zip(ids, embeddings)
    }


def export_candidate_pairs(out_path: Path = OUT_PATH) -> int:
    claims = get_all_claims()
    claims_by_id = {str(claim["id"]): claim for claim in claims}
    embeddings_by_doc_id = _load_embeddings(
        [_claim_doc_id(claim_id) for claim_id in claims_by_id]
    )

    rows = []
    seen_pairs = set()

    print(f"Starting export over {len(claims)} claims...")
    for idx, claim in enumerate(claims, 1):
        claim_id = str(claim["id"])
        claim_doc_id = _claim_doc_id(claim_id)

        for neighbor in find_similar_claims(claim["text"], n_results=N_NEIGHBORS):
            neighbor_id = neighbor["doc_id"].replace("claim_", "", 1)
            if claim_id == neighbor_id:
                continue

            pair_key = tuple(sorted([claim_id, neighbor_id]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            neighbor_claim = claims_by_id.get(neighbor_id)
            if neighbor_claim is None:
                continue

            if claim.get("arxiv_id", "") == neighbor_claim.get("arxiv_id", ""):
                continue

            rows.append({
                "claim_a_id": claim_id,
                "claim_b_id": neighbor_id,
                "claim_a_text": claim["text"],
                "claim_b_text": neighbor_claim["text"],
                "claim_a_embedding": json.dumps(embeddings_by_doc_id.get(claim_doc_id)),
                "claim_b_embedding": json.dumps(
                    embeddings_by_doc_id.get(neighbor["doc_id"])
                ),
                "distance": neighbor["distance"],
                "claim_a_arxiv_id": claim.get("arxiv_id", ""),
                "claim_b_arxiv_id": neighbor_claim.get("arxiv_id", ""),
                "claim_a_paper_title": claim.get("paper_title", ""),
                "claim_b_paper_title": neighbor_claim.get("paper_title", ""),
            })

        if idx % 200 == 0 or idx == len(claims):
            print(f"[{idx}/{len(claims)}] Processed claims | Unique candidate pairs so far: {len(rows)}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else [
            "claim_a_id",
            "claim_b_id",
            "claim_a_text",
            "claim_b_text",
            "claim_a_embedding",
            "claim_b_embedding",
            "distance",
            "claim_a_arxiv_id",
            "claim_b_arxiv_id",
            "claim_a_paper_title",
            "claim_b_paper_title",
        ])
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


if __name__ == "__main__":
    count = export_candidate_pairs()
    print(f"Exported {count} candidate pairs to {OUT_PATH}")
