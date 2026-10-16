"""
Export existing Neo4j CONTRADICTS and SUPPORTS relationships to eval/Data/existing_relationships.csv
and display the top 20 CONTRADICTS relationships by LLM confidence.
"""
import os
import sys
import csv
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from graph.neo4j_client import run_query


def export_existing_relationships():
    query = """
        MATCH (a:Claim)-[r:CONTRADICTS|SUPPORTS]->(b:Claim)
        RETURN elementId(a) AS claim_id_a,
               elementId(b) AS claim_id_b,
               a.text AS text_a,
               b.text AS text_b,
               type(r) AS relationship_type,
               coalesce(r.confidence, 0.0) AS llm_confidence
        ORDER BY relationship_type ASC, llm_confidence DESC
    """
    results = run_query(query)

    out_path = Path("eval/Data/existing_relationships.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = ["claim_id_a", "claim_id_b", "text_a", "text_b", "relationship_type", "llm_confidence"]

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"Exported {len(results)} existing relationships to {out_path}")

    # Separate counts
    contradicts = [r for r in results if r["relationship_type"] == "CONTRADICTS"]
    supports = [r for r in results if r["relationship_type"] == "SUPPORTS"]
    print(f"  CONTRADICTS: {len(contradicts)}")
    print(f"  SUPPORTS: {len(supports)}")

    # Sort CONTRADICTS by confidence descending
    contradicts_sorted = sorted(contradicts, key=lambda x: x["llm_confidence"], reverse=True)

    print("\n" + "=" * 90)
    print("TOP 20 AUTO-DETECTED 'CONTRADICTS' RELATIONSHIPS (SORTED BY LLM CONFIDENCE DESCENDING)")
    print("=" * 90 + "\n")

    for idx, row in enumerate(contradicts_sorted[:20], 1):
        conf = row["llm_confidence"]
        print(f"[{idx}] Confidence: {conf:.2f} | Claim A ID: {row['claim_id_a']} | Claim B ID: {row['claim_id_b']}")
        print(f"    CLAIM A: {row['text_a']}")
        print(f"    CLAIM B: {row['text_b']}")
        print("-" * 90)

    return len(results)


if __name__ == "__main__":
    export_existing_relationships()
