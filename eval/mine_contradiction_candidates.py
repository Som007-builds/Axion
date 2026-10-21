#!/usr/bin/env python
"""Mine likely genuine cross-paper contradiction candidates from the live graph.

Prompt 1 of the measurement plan. NO LLM calls, NO labels are generated or
pre-filled. Read-only against Neo4j + ChromaDB.

Rules
-----
rule1  different papers (`arxiv_id`), same normalized `subject` + `metric`,
       opposite `direction` (increase vs decrease).
rule2  different papers, same normalized `subject` + `metric`, numeric values
       in the claim texts differing by >10% relative. Numbers are found with a
       simple regex; the first non-year number in each text is used; pairs
       where either claim has no number are skipped.

Exclusions
----------
Every pair already reviewed in `eval/Data/axion_pairs.csv` is dropped, matched
on the unordered claim-id pair OR on the unordered normalized-text pair.

Ordering & output
-----------------
Ordered by rule strength (rule1+rule2, then rule1-only, then rule2-only), then
by ascending cosine distance computed from the stored ChromaDB claim
embeddings. Written to `eval/Data/contradiction_candidates_review.csv` with an
empty `human_label` column. The file deliberately contains NO judge verdicts,
NO confidence values and NO Neo4j edge types.

Id conventions (verified 2026-10-17, read-only probes)
------------------------------------------------------
* The canonical claim id is the Neo4j **elementId** (this is what
  `axion_pairs.csv` and the CONTRADICTS edges use).
* 2,135 of 2,389 claim embeddings are stored as ``claim_<elementId>``, but 254
  legacy claims (migrated from SQLite) are stored as ``claim_<int claim_id>``.
  Embedding lookup therefore tries ``claim_<elementId>`` first and falls back
  to the node's integer ``claim_id`` property.

Usage:
    python eval/mine_contradiction_candidates.py [--cap 150] [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from neo4j import GraphDatabase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
DATA_DIR = EVAL_DIR / "Data"
RESULTS_DIR = EVAL_DIR / "results"
REVIEW_DATASET = DATA_DIR / "axion_pairs.csv"
OUT_PATH = DATA_DIR / "contradiction_candidates_review.csv"
REPORT_PATH = RESULTS_DIR / "mining_contradiction_candidates_2026-10-17.json"

DEFAULT_CAP = 150
REL_DIFF_THRESHOLD = 0.10
PROGRESS_EVERY = 500

# direction value -> sign; None means "no usable polarity"
_DIRECTION_SIGNS: dict[str, int | None] = {
    "increases": 1, "increase": 1, "increased": 1, "increasing": 1,
    "higher": 1, "up": 1, "positive": 1, "improves": 1, "improve": 1,
    "improved": 1, "improvement": 1, "gains": 1, "gain": 1, "rise": 1, "rises": 1,
    "decreases": -1, "decrease": -1, "decreased": -1, "decreasing": -1,
    "lower": -1, "down": -1, "negative": -1, "reduces": -1, "reduce": -1,
    "reduced": -1, "reduction": -1, "worse": -1, "worsens": -1, "worsened": -1,
    "degrades": -1, "degrade": -1, "degraded": -1, "drop": -1, "drops": -1,
    "falls": -1,
    "no_effect": 0, "no effect": 0, "none": 0, "no change": 0, "no_change": 0,
    "unchanged": 0, "neutral": 0, "same": 0, "equal": 0, "no_impact": 0,
    "unclear": None, "unknown": None, "n/a": None, "na": None, "": None,
}

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
_YEAR_RE = re.compile(r"^(19|20)\d{2}$")
_THOUSANDS_RE = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
_WS_RE = re.compile(r"\s+")

CLAIMS_QUERY = """
MATCH (c:Claim)
OPTIONAL MATCH (c)-[:EXTRACTED_FROM]->(p:Paper)
RETURN elementId(c)  AS claim_id,
       c.claim_id    AS legacy_claim_id,
       c.text        AS text,
       c.section     AS section,
       c.subject     AS subject,
       c.metric      AS metric,
       c.direction   AS direction,
       p.arxiv_id    AS arxiv_id
"""


# ---------------------------------------------------------------------------
# small pure helpers
# ---------------------------------------------------------------------------

def _clean(value) -> str:
    """Stringify a possibly-NaN/None CSV cell."""
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def norm_key(value) -> str:
    """Normalize subject/metric for grouping: casefold + collapse whitespace."""
    if value is None:
        return ""
    return _WS_RE.sub(" ", str(value)).strip().casefold().strip(" .;:")


def norm_text(value) -> str:
    """Normalize claim text for order-insensitive pair matching."""
    if value is None:
        return ""
    return _WS_RE.sub(" ", str(value)).strip().casefold()


def direction_sign(value) -> tuple[int | None, bool]:
    """(sign, known). sign is +1/-1/0 or None (no usable polarity)."""
    key = norm_key(value)
    if key in _DIRECTION_SIGNS:
        return _DIRECTION_SIGNS[key], True
    if key:
        first = key.split(" ", 1)[0]
        if first in _DIRECTION_SIGNS:
            return _DIRECTION_SIGNS[first], True
    return None, False


def first_number(text) -> float | None:
    """First number in the text, skipping bare years (1900-2099)."""
    cleaned = _THOUSANDS_RE.sub("", str(text or ""))
    for match in _NUM_RE.finditer(cleaned):
        token = match.group(0)
        if _YEAR_RE.match(token):
            continue
        try:
            return float(token)
        except ValueError:
            continue
    return None


def relative_difference(a: float, b: float) -> float | None:
    """|a-b| / max(|a|,|b|); None when both are zero."""
    hi = max(abs(a), abs(b))
    if hi == 0:
        return None
    return abs(a - b) / hi


def dist_stats(values) -> dict:
    vs = sorted(v for v in values if v is not None)
    if not vs:
        return {"n": 0, "min": None, "median": None, "max": None}
    return {
        "n": len(vs),
        "min": round(vs[0], 6),
        "median": round(statistics.median(vs), 6),
        "max": round(vs[-1], 6),
    }


def rule_tier(rules: set[str]) -> int:
    """Sort order: strongest rule match first."""
    if "rule1" in rules and "rule2" in rules:
        return 0
    if "rule1" in rules:
        return 1
    return 2


# ---------------------------------------------------------------------------
# steps
# ---------------------------------------------------------------------------

def load_graph_claims() -> tuple[list[dict], dict, dict]:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        driver.verify_connectivity()
    except Exception as exc:  # noqa: BLE001
        print(f"[mine] Neo4j unreachable at {NEO4J_URI}: {exc}")
        raise SystemExit(2)

    coverage = {"subject": 0, "metric": 0, "both": 0, "direction": 0}
    with driver.session() as session:
        total = session.run("MATCH (c:Claim) RETURN count(c) AS n").single()["n"]
        print(f"[mine] claims in graph: {total}")
        claims: list[dict] = []
        by_id: dict[str, dict] = {}
        direction_counts: dict[str, int] = {}
        unmapped: dict[str, int] = {}
        for record in session.run(CLAIMS_QUERY):
            claim_id = record["claim_id"]
            if not claim_id:
                continue
            sign, known = direction_sign(record["direction"])
            raw_dir = norm_key(record["direction"])
            direction_counts[raw_dir or "(empty)"] = direction_counts.get(raw_dir or "(empty)", 0) + 1
            if raw_dir and not known:
                unmapped[raw_dir] = unmapped.get(raw_dir, 0) + 1
            subject_key = norm_key(record["subject"])
            metric_key = norm_key(record["metric"])
            if subject_key:
                coverage["subject"] += 1
            if metric_key:
                coverage["metric"] += 1
            if subject_key and metric_key:
                coverage["both"] += 1
            if str(record["direction"] or "").strip():
                coverage["direction"] += 1
            claim = {
                "claim_id": claim_id,
                "legacy_claim_id": record["legacy_claim_id"],
                "text": record["text"] or "",
                "section": record["section"] or "",
                "subject": record["subject"] or "",
                "metric": record["metric"] or "",
                "direction": record["direction"] or "",
                "arxiv_id": record["arxiv_id"] or "",
                "subject_key": subject_key,
                "metric_key": metric_key,
                "sign": sign,
                "number": first_number(record["text"]),
            }
            claims.append(claim)
            by_id[claim_id] = claim
            if len(claims) % PROGRESS_EVERY == 0:
                print(f"[mine] loaded claims: {len(claims)}/{total}")
    driver.close()
    return claims, by_id, {"coverage": coverage, "direction_counts": direction_counts,
                           "unmapped": unmapped}


def relaxed_preview(claims: list[dict]) -> dict:
    """Report-only yield preview if subject (or metric) alone were used."""
    def cross_pairs(key: str) -> tuple[int, int]:
        groups: dict[str, list[dict]] = {}
        for claim in claims:
            if claim[key]:
                groups.setdefault(claim[key], []).append(claim)
        count = 0
        for members in groups.values():
            n = len(members)
            for i in range(n):
                for j in range(i + 1, n):
                    ai, aj = members[i]["arxiv_id"], members[j]["arxiv_id"]
                    if ai and aj and ai != aj:
                        count += 1
        return count, len(groups)

    subject_only, subject_groups = cross_pairs("subject_key")
    metric_only, metric_groups = cross_pairs("metric_key")
    return {
        "same_subject_only_cross_paper_pairs": subject_only,
        "same_subject_only_groups": subject_groups,
        "same_metric_only_cross_paper_pairs": metric_only,
        "same_metric_only_groups": metric_groups,
    }


def scan_rules(claims: list[dict]) -> tuple[dict, dict]:
    """Return (found: pair -> set(rules), stats dict)."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for claim in claims:
        if claim["subject_key"] and claim["metric_key"]:
            groups.setdefault((claim["subject_key"], claim["metric_key"]), []).append(claim)
    eligible = sum(len(members) for members in groups.values())
    print(f"[mine] claims with subject+metric: {eligible} in {len(groups)} groups")

    found: dict[tuple[str, str], set[str]] = {}
    same_key_cross_paper = 0
    processed = 0
    for members in groups.values():
        n = len(members)
        for i in range(n):
            a = members[i]
            processed += 1
            if processed % PROGRESS_EVERY == 0:
                print(f"[mine] rule scan: {processed}/{eligible} claims processed, "
                      f"{len(found)} candidate pairs so far")
            for j in range(i + 1, n):
                b = members[j]
                if (not a["arxiv_id"] or not b["arxiv_id"]
                        or a["arxiv_id"] == b["arxiv_id"]):
                    continue
                same_key_cross_paper += 1
                pair = ((a["claim_id"], b["claim_id"]) if a["claim_id"] <= b["claim_id"]
                        else (b["claim_id"], a["claim_id"]))
                r1 = (a["sign"] is not None and b["sign"] is not None
                      and a["sign"] * b["sign"] == -1)
                rd = None
                if a["number"] is not None and b["number"] is not None:
                    rd = relative_difference(a["number"], b["number"])
                r2 = rd is not None and rd > REL_DIFF_THRESHOLD
                if r1 or r2:
                    rules = found.setdefault(pair, set())
                    if r1:
                        rules.add("rule1")
                    if r2:
                        rules.add("rule2")

    stats = {
        "eligible_claims": eligible,
        "groups": len(groups),
        "same_key_cross_paper_pairs": same_key_cross_paper,
        "rule1_pairs": sum(1 for r in found.values() if "rule1" in r),
        "rule2_pairs": sum(1 for r in found.values() if "rule2" in r),
        "rule1_and_rule2": sum(1 for r in found.values() if r == {"rule1", "rule2"}),
        "unique_pairs": len(found),
    }
    return found, stats


def load_reviewed_pairs() -> tuple[pd.DataFrame, str, set, set]:
    df = pd.read_csv(REVIEW_DATASET)
    label_col = "label" if "label" in df.columns else "human_label"
    id_pairs: set[tuple[str, str]] = set()
    text_pairs: set[tuple[str, str]] = set()
    for row in df.itertuples(index=False):
        a_id, b_id = _clean(row.claim_a_id), _clean(row.claim_b_id)
        if a_id and b_id:
            id_pairs.add(tuple(sorted((a_id, b_id))))
        a_tx, b_tx = norm_text(row.claim_a_text), norm_text(row.claim_b_text)
        if a_tx and b_tx:
            text_pairs.add(tuple(sorted((a_tx, b_tx))))
    return df, label_col, id_pairs, text_pairs


def compute_distances(kept: dict, by_id: dict) -> tuple[dict, dict, int, int, int, str]:
    """Cosine distances from stored embeddings.

    Embedding lookup: ``claim_<elementId>`` first, then ``claim_<int claim_id>``
    for the 254 legacy-migrated claims.
    """
    from embeddings.store import _claims_col  # local import: opens ChromaDB lazily

    col = _claims_col()
    claims_needed = sorted({cid for pair in kept for cid in pair})
    doc_candidates: dict[str, list[str]] = {}
    all_docs: set[str] = set()
    for cid in claims_needed:
        candidates = [f"claim_{cid}"]
        legacy = by_id[cid].get("legacy_claim_id")
        if isinstance(legacy, int) and not isinstance(legacy, bool):
            candidates.append(f"claim_{legacy}")
        doc_candidates[cid] = candidates
        all_docs.update(candidates)

    data = col.get(ids=sorted(all_docs), include=["embeddings"], limit=len(all_docs))
    by_doc = {doc_id: np.asarray(vec, dtype=float)
              for doc_id, vec in zip(data["ids"], data["embeddings"])}
    embeddings: dict[str, np.ndarray] = {}
    fallback_used = 0
    for cid, candidates in doc_candidates.items():
        for index, doc_id in enumerate(candidates):
            if doc_id in by_doc:
                embeddings[cid] = by_doc[doc_id]
                if index > 0:
                    fallback_used += 1
                break
    missing = len(claims_needed) - len(embeddings)

    distances: dict[tuple[str, str], float | None] = {}
    for pair in kept:
        va, vb = embeddings.get(pair[0]), embeddings.get(pair[1])
        if va is None or vb is None:
            distances[pair] = None
            continue
        na, nb = np.linalg.norm(va), np.linalg.norm(vb)
        if na == 0 or nb == 0:
            distances[pair] = None
            continue
        distances[pair] = 1.0 - float(va @ vb / (na * nb))
    return (distances, embeddings, len(claims_needed), missing, fallback_used,
            str(getattr(col, "metadata", None)))


def chroma_id_convention_stats() -> dict | None:
    """Report how claim embeddings are keyed (elementId vs legacy int)."""
    try:
        from embeddings.store import _claims_col
        col = _claims_col()
        ids = col.get(limit=200_000, include=[])["ids"]
        element_style = sum(1 for i in ids if i.startswith("claim_") and ":" in i)
        int_style = sum(1 for i in ids
                        if i.startswith("claim_") and i[len("claim_"):].isdigit())
        return {
            "total": len(ids),
            "elementId_style": element_style,
            "legacy_int_style": int_style,
            "other": len(ids) - element_style - int_style,
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def distance_space_probe(col, embeddings: dict, kept: dict) -> list[dict]:
    """Compare Chroma's returned distance to the manual 1-cosine for a few pairs."""
    probes = []
    for pair in list(kept.keys()):
        if len(probes) >= 3:
            break
        va, vb = embeddings.get(pair[0]), embeddings.get(pair[1])
        if va is None or vb is None:
            continue
        res = col.query(query_embeddings=[va.tolist()], n_results=8,
                        include=["distances"])
        lookup = {cid: dist for cid, dist in
                  zip(res["ids"][0], res["distances"][0])}
        b_doc = f"claim_{pair[1]}"
        if b_doc not in lookup:
            continue
        manual = 1.0 - float(va @ vb / (np.linalg.norm(va) * np.linalg.norm(vb)))
        probes.append({
            "pair": pair,
            "chroma_distance": round(float(lookup[b_doc]), 6),
            "manual_cosine_distance": round(manual, 6),
            "ratio": round(float(lookup[b_doc]) / manual, 4) if manual else None,
        })
    return probes


def build_rows(kept: dict, distances: dict, by_id: dict) -> list[dict]:
    rows = []
    for pair, rules in kept.items():
        dist = distances.get(pair)
        a, b = by_id[pair[0]], by_id[pair[1]]
        source = ("rule1+rule2" if rules == {"rule1", "rule2"}
                  else next(iter(rules)))
        rows.append({
            "claim_id_a": pair[0],
            "claim_id_b": pair[1],
            "arxiv_id_a": a["arxiv_id"],
            "arxiv_id_b": b["arxiv_id"],
            "text_a": _WS_RE.sub(" ", a["text"]).strip(),
            "text_b": _WS_RE.sub(" ", b["text"]).strip(),
            "section_a": _WS_RE.sub(" ", a["section"]).strip(),
            "section_b": _WS_RE.sub(" ", b["section"]).strip(),
            "subject": a["subject_key"],
            "metric": a["metric_key"],
            "direction_a": a["direction"],
            "direction_b": b["direction"],
            "cosine_distance": dist,
            "source_rule": source,
            "_tier": rule_tier(rules),
        })
    rows.sort(key=lambda r: (
        r["_tier"],
        r["cosine_distance"] if r["cosine_distance"] is not None else float("inf"),
        r["claim_id_a"], r["claim_id_b"],
    ))
    return rows


def sanity_check(df: pd.DataFrame, label_col: str, by_id: dict) -> list[dict]:
    """Rule-coverage check on the reviewed CONTRADICTS rows (report only)."""
    positives = df[df[label_col].astype(str).str.strip().str.upper() == "CONTRADICTS"]
    results = []
    for row in positives.itertuples(index=False):
        a_id, b_id = _clean(row.claim_a_id), _clean(row.claim_b_id)
        entry: dict = {
            "pair_id": _clean(row.pair_id),
            "claim_id_a": a_id,
            "claim_id_b": b_id,
        }
        a, b = by_id.get(a_id), by_id.get(b_id)
        if a is None or b is None:
            entry["in_live_graph"] = False
            entry["note"] = "claim(s) not found in the live graph"
            results.append(entry)
            continue
        entry["in_live_graph"] = True
        same_key = bool(
            a["subject_key"] and b["subject_key"]
            and a["subject_key"] == b["subject_key"]
            and a["metric_key"] and b["metric_key"]
            and a["metric_key"] == b["metric_key"]
        )
        signs_opposite = (
            a["sign"] is not None and b["sign"] is not None
            and a["sign"] * b["sign"] == -1
        )
        rd = None
        if a["number"] is not None and b["number"] is not None:
            rd = relative_difference(a["number"], b["number"])
        entry.update({
            "subject_a": a["subject"], "subject_b": b["subject"],
            "metric_a": a["metric"], "metric_b": b["metric"],
            "direction_a": a["direction"], "direction_b": b["direction"],
            "subject_metric_present_a": bool(a["subject_key"] and a["metric_key"]),
            "subject_metric_present_b": bool(b["subject_key"] and b["metric_key"]),
            "number_a": a["number"], "number_b": b["number"],
            "relative_difference": round(rd, 6) if rd is not None else None,
            "same_subject_and_metric": same_key,
            "rule1_hit": bool(same_key and signs_opposite),
            "rule1_reason": ("opposite direction signs" if same_key and signs_opposite
                             else "subject/metric absent or direction not opposite/known"),
            "rule2_hit": bool(same_key and rd is not None
                              and rd > REL_DIFF_THRESHOLD),
            "rule2_reason": ("numeric difference >10%"
                             if same_key and rd is not None
                             and rd > REL_DIFF_THRESHOLD
                             else "subject/metric absent, no numeric pair, "
                                  "or difference <=10%"),
        })
        results.append(entry)
    return results


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description="Mine contradiction candidates (no LLM).")
    parser.add_argument("--cap", type=int, default=DEFAULT_CAP,
                        help=f"max rows written to the review CSV (default {DEFAULT_CAP})")
    parser.add_argument("--dry-run", action="store_true",
                        help="print everything but write no files")
    args = parser.parse_args()

    print("=== Axion candidate mining (no LLM calls, no labels) ===")
    print(f"[mine] Neo4j: {NEO4J_URI}")

    df, label_col, id_pairs, text_pairs = load_reviewed_pairs()
    print(f"[mine] reviewed dataset: {REVIEW_DATASET} "
          f"({len(df)} rows, label column '{label_col}', "
          f"{len(id_pairs)} id-pairs, {len(text_pairs)} text-pairs)")

    claims, by_id, graph_info = load_graph_claims()

    coverage = graph_info["coverage"]
    print(f"[mine] structured-field coverage of {len(claims)} claims: "
          f"subject non-empty {coverage['subject']}, metric non-empty {coverage['metric']}, "
          f"subject+metric {coverage['both']}, direction non-empty {coverage['direction']}")
    print("[mine] direction values (normalized -> count):")
    for value, count in sorted(graph_info["direction_counts"].items(),
                               key=lambda kv: -kv[1]):
        sign, known = direction_sign(value if value != "(empty)" else "")
        tag = "" if not value or value == "(empty)" else (
            " -> +1" if sign == 1 else " -> -1" if sign == -1
            else " -> 0" if sign == 0 and known else "")
        print(f"         {value!r}: {count}{tag}")
    if graph_info["unmapped"]:
        print(f"[mine] UNMAPPED direction values: {graph_info['unmapped']}")

    found, stats = scan_rules(claims)
    print(f"[mine] rule1 raw pairs: {stats['rule1_pairs']}")
    print(f"[mine] rule2 raw pairs: {stats['rule2_pairs']}")
    print(f"[mine] rule1+rule2 overlap: {stats['rule1_and_rule2']}")
    print(f"[mine] unique raw candidate pairs: {stats['unique_pairs']}")

    preview = relaxed_preview(claims)
    print(f"[mine] relaxed preview (report only, NOT written to the review file): "
          f"same-subject-only cross-paper pairs {preview['same_subject_only_cross_paper_pairs']} "
          f"in {preview['same_subject_only_groups']} groups; "
          f"same-metric-only cross-paper pairs {preview['same_metric_only_cross_paper_pairs']} "
          f"in {preview['same_metric_only_groups']} groups")

    excluded_ids = excluded_text = 0
    kept: dict[tuple[str, str], set[str]] = {}
    for pair, rules in found.items():
        if pair in id_pairs:
            excluded_ids += 1
            continue
        a, b = by_id[pair[0]], by_id[pair[1]]
        norm_pair = tuple(sorted((norm_text(a["text"]), norm_text(b["text"]))))
        if norm_pair in text_pairs:
            excluded_text += 1
            continue
        kept[pair] = rules
    print(f"[mine] excluded (already reviewed): {excluded_ids} by claim ids, "
          f"{excluded_text} by text only -> {len(kept)} candidates remain")
    after = {
        "rule1+rule2": sum(1 for r in kept.values() if r == {"rule1", "rule2"}),
        "rule1_only": sum(1 for r in kept.values() if r == {"rule1"}),
        "rule2_only": sum(1 for r in kept.values() if r == {"rule2"}),
    }
    print(f"[mine] candidates by rule after exclusion: {after}")

    id_stats = chroma_id_convention_stats()
    if id_stats and "error" not in id_stats:
        print(f"[mine] ChromaDB claim-id conventions: {id_stats}")
    else:
        print(f"[mine] ChromaDB id-convention probe skipped: {id_stats}")

    embeddings: dict[str, np.ndarray] = {}
    missing = fallback_used = 0
    col_meta = None
    if kept:
        (distances, embeddings, involved, missing, fallback_used,
         col_meta) = compute_distances(kept, by_id)
        print(f"[mine] embeddings: {involved - missing}/{involved} candidate claims found "
              f"in ChromaDB ({missing} missing, {fallback_used} via legacy-int fallback)")
    else:
        distances = {}
    rows = build_rows(kept, distances, by_id) if kept else []
    written = rows[: max(args.cap, 0)]
    all_stats = dist_stats(r["cosine_distance"] for r in rows)
    written_stats = dist_stats(r["cosine_distance"] for r in written)
    remaining = len(rows) - len(written)
    remaining_by_tier = {
        "rule1+rule2": len([r for r in rows[len(written):] if r["source_rule"] == "rule1+rule2"]),
        "rule1": len([r for r in rows[len(written):] if r["source_rule"] == "rule1"]),
        "rule2": len([r for r in rows[len(written):] if r["source_rule"] == "rule2"]),
    }
    if rows:
        print(f"[mine] distance min/median/max over ALL candidates: "
              f"{all_stats['min']}/{all_stats['median']}/{all_stats['max']}")
    else:
        print("[mine] distance min/median/max over ALL candidates: n/a (0 pairs)")
    verb = "would write" if args.dry_run else "writing"
    print(f"[mine] {verb} {len(written)} rows (cap {args.cap}); "
          f"{remaining} more exist beyond the cap {remaining_by_tier}")
    if written:
        print(f"[mine] distance min/median/max in the written file: "
              f"{written_stats['min']}/{written_stats['median']}/{written_stats['max']}")
    else:
        print("[mine] distance min/median/max in the written file: n/a")

    probes: list[dict] = []
    if kept:
        try:
            from embeddings.store import _claims_col
            col = _claims_col()
            col_meta = str(col.metadata)
            probes = distance_space_probe(col, embeddings, kept)
        except Exception as exc:  # noqa: BLE001
            print(f"[mine] distance-space probe skipped: {exc}")
        if probes:
            print(f"[mine] distance-space probe (collection metadata: {col_meta}):")
            for probe in probes:
                print(f"         chroma={probe['chroma_distance']} vs manual "
                      f"1-cos={probe['manual_cosine_distance']} "
                      f"(ratio {probe['ratio']})")

    if not args.dry_run:
        with open(OUT_PATH, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow([
                "pair_id", "claim_id_a", "claim_id_b", "arxiv_id_a", "arxiv_id_b",
                "text_a", "text_b", "section_a", "section_b", "subject", "metric",
                "direction_a", "direction_b", "cosine_distance", "source_rule",
                "human_label",
            ])
            for index, row in enumerate(written, start=1):
                writer.writerow([
                    f"cand_{index:04d}", row["claim_id_a"], row["claim_id_b"],
                    row["arxiv_id_a"], row["arxiv_id_b"], row["text_a"],
                    row["text_b"], row["section_a"], row["section_b"],
                    row["subject"], row["metric"], row["direction_a"],
                    row["direction_b"],
                    "" if row["cosine_distance"] is None
                    else f"{row['cosine_distance']:.6f}",
                    row["source_rule"], "",
                ])
        print(f"[mine] wrote {OUT_PATH} ({len(written)} data rows)")

    print("\n=== Top 10 pairs with full text ===")
    if not written:
        print("[mine] none (0 candidate pairs)")
    for index, row in enumerate(written[:10], start=1):
        dist = row["cosine_distance"]
        print(f"\n[{index}] {row['source_rule']}  cosine_distance="
              f"{'n/a' if dist is None else f'{dist:.4f}'}")
        print(f"  A {row['claim_id_a']}  ({row['arxiv_id_a']}, {row['section_a']})  "
              f"subject={row['subject']!r} metric={row['metric']!r} "
              f"direction={row['direction_a']!r}")
        print(f"    {row['text_a']}")
        print(f"  B {row['claim_id_b']}  ({row['arxiv_id_b']}, {row['section_b']})  "
              f"subject={row['subject']!r} metric={row['metric']!r} "
              f"direction={row['direction_b']!r}")
        print(f"    {row['text_b']}")

    check = sanity_check(df, label_col, by_id)
    print("\n=== Sanity check: reviewed CONTRADICTS rows vs mining rules "
          "(report only; these pairs are excluded from the review file) ===")
    print(f"[mine] rows with {label_col} == CONTRADICTS: {len(check)}")
    for entry in check:
        print(f"\n  pair_id={entry['pair_id']}  "
              f"({entry['claim_id_a']} , {entry['claim_id_b']})")
        if not entry.get("in_live_graph"):
            print(f"    {entry.get('note')}")
            continue
        print(f"    subject: A={entry['subject_a']!r} B={entry['subject_b']!r} | "
              f"metric: A={entry['metric_a']!r} B={entry['metric_b']!r}")
        print(f"    direction: A={entry['direction_a']!r} B={entry['direction_b']!r} | "
              f"numbers: A={entry['number_a']} B={entry['number_b']} "
              f"(rel diff {entry['relative_difference']})")
        print(f"    rule1 (opposite direction): {entry['rule1_hit']} "
              f"[{entry['rule1_reason']}]")
        print(f"    rule2 (numeric diff >10%): {entry['rule2_hit']} "
              f"[{entry['rule2_reason']}]")

    report = {
        "generated_at": date.today().isoformat(),
        "script": "eval/mine_contradiction_candidates.py",
        "model": "none — no LLM calls were made",
        "gate_value": "not applied — mining is independent of CONTRADICTION_MAX_DISTANCE",
        "prompt_hash": "n/a — no prompt used",
        "dataset": {
            "path": str(REVIEW_DATASET),
            "rows": int(len(df)),
            "label_column": label_col,
            "used_for": ["exclusions", "rule-coverage sanity check"],
        },
        "graph_claims": len(claims),
        "structured_field_coverage": coverage,
        "claims_with_subject_and_metric": stats["eligible_claims"],
        "groups": stats["groups"],
        "same_key_cross_paper_pairs": stats["same_key_cross_paper_pairs"],
        "rule_raw_counts": {
            "rule1": stats["rule1_pairs"],
            "rule2": stats["rule2_pairs"],
            "rule1_and_rule2": stats["rule1_and_rule2"],
            "unique": stats["unique_pairs"],
        },
        "relaxed_preview_report_only": preview,
        "excluded_by_reviewed_set": {
            "by_claim_ids": excluded_ids,
            "by_text_only": excluded_text,
            "total": excluded_ids + excluded_text,
        },
        "candidates_after_exclusions": {**after, "total": len(kept)},
        "written": {
            "path": str(OUT_PATH),
            "rows": 0 if args.dry_run else len(written),
            "cap": args.cap,
            "distance": written_stats,
            "remaining_beyond_cap": remaining,
            "remaining_by_rule": remaining_by_tier,
        },
        "distance_all_candidates": all_stats,
        "embedding_coverage": {"candidate_claims": len(embeddings) if kept else 0,
                               "missing": missing,
                               "legacy_int_fallback_used": fallback_used},
        "chroma_id_conventions": id_stats,
        "chroma_collection_metadata": col_meta,
        "distance_space_probes": probes,
        "direction_value_counts": graph_info["direction_counts"],
        "direction_unmapped_values": graph_info["unmapped"],
        "sanity_check_reviewed_contradicts": check,
    }
    if not args.dry_run:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        with open(REPORT_PATH, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)
        print(f"\n[mine] wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
