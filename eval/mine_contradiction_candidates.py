#!/usr/bin/env python
"""Mine likely genuine cross-paper contradiction candidates from the live graph.

NO LLM calls. NO labels are generated or pre-filled. Read-only against
Neo4j + ChromaDB.

Modes
-----
``--mode text`` (default)
    Candidate pool: unique cross-paper pairs among the top-8 retrieval
    neighbours of every claim, cosine distance <= 0.55 (wider than the 0.35
    production gate on purpose). Pairs already reviewed in
    ``eval/Data/axion_pairs.csv`` (by claim ids or normalized text), exact
    duplicate texts, empty texts, and pairs with distance < 0.05 are excluded.

    Every pair is scored with five independent signals (binary each):
      1 shared benchmark/dataset token (regex-extracted name tokens matched
        against an explicit list printed in the results JSON)
      2 shared model/method name token (name-shaped token in both claims that
        is not a benchmark token)
      3 opposite polarity vocabulary across the two claims (explicit word
        lists printed in the report)
      4 numeric disagreement: both claims have a number within 120 characters
        of the same shared name token, relative difference > 10%
      5 structured fields: same subject, same metric, opposite direction
        (rare; counted but not depended upon)

    Ranked by score descending, then cosine distance ascending, with at most
    5 pairs per unordered paper pair. The top ``--cap`` (default 150) are
    written best-first to ``eval/human_review/contradiction_candidates_review.csv``
    with an EMPTY ``human_label`` column. Signal details and scores go to
    ``eval/results/mining_signals_<date>.json``.

``--mode structured`` (original Prompt-1 behaviour, kept behind a flag)
    rule1  different papers, same normalized ``subject`` + ``metric``, opposite
           ``direction``.
    rule2  different papers, same normalized ``subject`` + ``metric``, first
           non-year number in each claim text differing by >10% relative.
    Writes ``eval/Data/contradiction_candidates_review.csv`` (16 columns) and
    ``eval/results/mining_contradiction_candidates_2026-10-17.json``.

Id conventions (verified 2026-10-17, read-only probes)
------------------------------------------------------
* The canonical claim id is the Neo4j **elementId** (this is what
  ``axion_pairs.csv`` and the CONTRADICTS edges use).
* 2,135 of 2,389 claim embeddings are stored as ``claim_<elementId>``, but 254
  legacy claims (migrated from SQLite) are stored as ``claim_<int claim_id>``.
  Embedding lookup therefore tries ``claim_<elementId>`` first and falls back
  to the node's integer ``claim_id`` property.

Usage:
    python eval/mine_contradiction_candidates.py [--mode text] [--cap 150] [--dry-run]
    python eval/mine_contradiction_candidates.py --mode structured [--cap 150] [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import sys
from collections import Counter
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
HUMAN_REVIEW_DIR = EVAL_DIR / "human_review"
REVIEW_DATASET = DATA_DIR / "axion_pairs.csv"

# structured-mode outputs (kept exactly as shipped in Prompt 1)
OUT_PATH = DATA_DIR / "contradiction_candidates_review.csv"
REPORT_PATH = RESULTS_DIR / "mining_contradiction_candidates_2026-10-17.json"

# text-mode outputs
TEXT_OUT_PATH = HUMAN_REVIEW_DIR / "contradiction_candidates_review.csv"
TEXT_REPORT_PATH = RESULTS_DIR / f"mining_signals_{date.today().isoformat()}.json"

DEFAULT_CAP = 150
REL_DIFF_THRESHOLD = 0.10
PROGRESS_EVERY = 500

# text-mode parameters
POOL_DISTANCE = 0.55
MIN_PAIR_DISTANCE = 0.05
PER_PAPER_PAIR_CAP = 5
TOP_NEIGHBORS = 8
NUMERIC_WINDOW = 120

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

# name-shaped tokens: GSM8K, MMLU, SCAN, HellaSwag, WikiText-103, GPT-4, ...
_NAME_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"([A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*)"
    r"(?![A-Za-z0-9_])"
)
# numbers with optional thousands separators, not glued to alphanumerics
_NUM_POS_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?)"
    r"(?![A-Za-z0-9])"
)

# Explicit benchmark/dataset list. Classification is only applied to tokens
# that already look like names (see _is_name_like), so lowercase common words
# such as "scan" or "drop" do not become name tokens by themselves.
BENCHMARK_TOKENS = frozenset({
    "gsm8k", "gsm-8k", "svamp", "asdiv", "math500", "mathvista", "mathvision",
    "mmlu", "mmlu-pro", "mmlu-redux", "hellaswag", "scan", "wikitext",
    "wikitext-103", "wikitext-2", "wt103", "squad", "squad2", "squad-2",
    "glue", "superglue", "arc", "arc-easy", "arc-challenge", "boolq", "piqa",
    "winogrande", "truthfulqa", "humaneval", "mbpp", "openbookqa",
    "commonsenseqa", "bbh", "bigbench", "big-bench", "triviaqa",
    "naturalquestions", "webqs", "webquestions", "lambada", "ptb", "enwik8",
    "imagenet", "cifar-10", "cifar-100", "coco", "vqa", "gqa", "textvqa",
    "docvqa", "chartqa", "scienceqa", "tabfact", "anli", "rte", "cola",
    "sst-2", "mrpc", "qqp", "mnli", "qnli", "wnli", "sts-b", "wmt", "iwslt",
    "librispeech", "commonvoice", "alpacaeval", "alpaca-eval", "mt-bench",
    "mtbench", "chatbot-arena", "lmsys", "mmmu", "mmmu-pro", "videomme",
    "longvideobench", "olympiadbench", "aime", "gpqa", "livecodebench",
    "swe-bench", "swebench", "terminal-bench", "codeforces", "medqa",
    "pubmedqa", "legalbench", "ifeval", "arena-hard", "rewardbench", "mujoco",
    "atari", "dm-control", "procgen", "minigrid", "babyai", "alfworld",
    "webshop", "scienceworld", "textworld", "jericho", "hotpotqa", "musique",
    "qasper", "govreport", "xsum", "samsum", "cnn-dailymail", "writingprompt",
    "multi-news", "billsum", "scitldr",
})

# Generic acronyms that look like names but carry no model/benchmark identity.
GENERIC_NAME_TOKENS = frozenset({
    "ai", "ml", "nlp", "llm", "llms", "api", "apis", "gpu", "gpus", "cpu",
    "tpu", "rq", "json", "csv", "pdf", "html", "http", "https", "url",
    "sota", "f1", "em", "bleu", "rouge", "meteor", "bertscore", "auc",
    "map", "mrr", "ndcg", "wer", "cer", "ppl", "id", "ids", "ok", "vs",
    "ii", "iii", "iv",
})

POLARITY_POSITIVE = (
    "improve", "improves", "improved", "improving", "improvement",
    "outperform", "outperforms", "outperformed", "outperforming",
    "better", "higher", "increase", "increases", "increased", "increasing",
    "gain", "gains", "gained", "help", "helps", "helped", "effective",
    "superior", "exceed", "exceeds", "exceeded", "boost", "boosts", "boosted",
    "enhance", "enhances", "enhanced", "win", "wins", "won", "success",
    "succeeds", "stronger", "faster",
)
POLARITY_NEGATIVE = (
    "degrade", "degrades", "degraded", "degrading", "degradation",
    "hurt", "hurts", "underperform", "underperforms", "underperformed",
    "worse", "lower", "decrease", "decreases", "decreased", "decreasing",
    "loss", "losses", "lose", "loses", "lost", "fail", "fails", "failed",
    "failing", "failure", "ineffective", "inferior", "harm", "harms",
    "worsen", "worsens", "worsened", "reduce", "reduces", "reduced",
    "drop", "drops", "dropped", "weaker", "slower", "struggle", "struggles",
    "struggled",
)


def _alternation(words) -> re.Pattern:
    body = "|".join(sorted((re.escape(w) for w in words), key=len, reverse=True))
    return re.compile(rf"\b(?:{body})\b", re.IGNORECASE)


_POS_RE = _alternation(POLARITY_POSITIVE)
_NEG_RE = _alternation(POLARITY_NEGATIVE)

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


def _is_name_like(raw: str) -> bool:
    """True for GSM8K / MMLU / HellaSwag / WikiText-103 style name tokens."""
    if len(raw) < 2:
        return False
    if raw.casefold() in GENERIC_NAME_TOKENS:
        return False
    if any(ch.isdigit() for ch in raw):
        return True
    if any(ch.isupper() for ch in raw[1:]):
        return True
    return raw.isupper()


def claim_features(text: str) -> dict:
    """Cache token/position/number/polarity features for one claim text."""
    text = str(text or "")
    tokens: dict[str, str] = {}
    positions: dict[str, list[tuple[int, int]]] = {}
    spans: list[tuple[int, int]] = []
    for match in _NAME_TOKEN_RE.finditer(text):
        raw = match.group(1)
        spans.append(match.span(1))
        if not _is_name_like(raw):
            continue
        key = raw.casefold()
        tokens.setdefault(key, raw)
        positions.setdefault(key, []).append(match.span(1))

    numbers: list[tuple[float, int]] = []
    for match in _NUM_POS_RE.finditer(text):
        raw = match.group(1)
        start, end = match.span(1)
        if any(s <= start < e or s < end <= e for s, e in spans):
            continue
        if _YEAR_RE.match(raw.lstrip("-").replace(",", "")):
            continue
        if start >= 1 and text[start - 1] == "[" and end < len(text) and text[end] == "]":
            continue
        if start >= 2 and text[start - 1] == "." and text[start - 2].isalnum():
            continue  # version number such as Qwen2.5
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        numbers.append((value, start))

    return {
        "tokens": tokens,
        "positions": positions,
        "numbers": numbers,
        "positive": {m.group(0).casefold() for m in _POS_RE.finditer(text)},
        "negative": {m.group(0).casefold() for m in _NEG_RE.finditer(text)},
    }


def _nearest_number(feature: dict, token_key: str,
                    window: int = NUMERIC_WINDOW) -> tuple[float, float] | None:
    """(char-distance, value) of the closest number to any occurrence of token."""
    best: tuple[float, float] | None = None
    for start, end in feature["positions"].get(token_key, ()):
        for value, pos in feature["numbers"]:
            distance = min(abs(pos - start), abs(pos - end))
            if distance <= window and (best is None or distance < best[0]):
                best = (float(distance), value)
    return best


def cosine_distance(a: np.ndarray, b: np.ndarray) -> float | None:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return None
    return 1.0 - float(a @ b / (na * nb))


# ---------------------------------------------------------------------------
# common steps
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


# ---------------------------------------------------------------------------
# structured mode (original Prompt-1 behaviour, unchanged except for dispatch)
# ---------------------------------------------------------------------------

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


def compute_distances(kept: dict, by_id: dict) -> tuple[dict, dict, int, int, int, str]:
    """Cosine distances from stored embeddings (structured mode)."""
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


def run_structured(args) -> int:
    """Original Prompt-1 structured-field miner (0 pairs on the current graph)."""
    print("=== Axion structured candidate mining (no LLM calls, no labels) ===")
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
        "mode": "structured",
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


# ---------------------------------------------------------------------------
# text-heuristic mode
# ---------------------------------------------------------------------------

def load_claim_vectors(claims: list[dict]):
    """Return (collection, claim_vec, doc_to_claim, missing, fallback_used, docs)."""
    from embeddings.store import _claims_col  # local import: opens ChromaDB lazily

    col = _claims_col()
    data = col.get(include=["embeddings"], limit=200_000)
    doc_vec = {doc: np.asarray(vec, dtype=float)
               for doc, vec in zip(data["ids"], data["embeddings"])}

    claim_vec: dict[str, np.ndarray] = {}
    doc_to_claim: dict[str, str] = {}
    fallback_used = 0
    for claim in claims:
        legacy = claim.get("legacy_claim_id")
        candidates = [f"claim_{claim['claim_id']}"]
        if isinstance(legacy, int) and not isinstance(legacy, bool):
            candidates.append(f"claim_{legacy}")
        for index, doc_id in enumerate(candidates):
            if doc_id in doc_vec:
                claim_vec[claim["claim_id"]] = doc_vec[doc_id]
                doc_to_claim[doc_id] = claim["claim_id"]
                if index > 0:
                    fallback_used += 1
                break
    missing = [c["claim_id"] for c in claims if c["claim_id"] not in claim_vec]
    return col, claim_vec, doc_to_claim, missing, fallback_used, len(doc_vec)


def build_retrieval_pool(claims: list[dict], claim_vec: dict, doc_to_claim: dict,
                         by_id: dict, col, pool_distance: float,
                         top_n: int) -> tuple[dict, dict]:
    """Top-N neighbour pairs, deduped, cross-paper, distance <= pool_distance."""
    stats = {
        "claims_queried": 0,
        "neighbor_slots": 0,
        "unresolved_neighbor_ids": 0,
        "self_hits": 0,
        "same_paper_hits": 0,
        "missing_arxiv_hits": 0,
        "above_pool_distance_hits": 0,
        "unique_pairs_within_distance": 0,
    }
    pairs: dict[tuple[str, str], float] = {}
    ids = [c["claim_id"] for c in claims if c["claim_id"] in claim_vec]
    batch_size = 250  # 2 batches = exactly 500 claims per progress line
    last_report = 0

    for start in range(0, len(ids), batch_size):
        chunk = ids[start:start + batch_size]
        result = col.query(
            query_embeddings=[claim_vec[cid].tolist() for cid in chunk],
            n_results=top_n,
            include=["distances"],
        )
        for cid, row_ids, row_dists in zip(chunk, result["ids"], result["distances"]):
            stats["claims_queried"] += 1
            stats["neighbor_slots"] += len(row_ids)
            a = by_id[cid]
            for doc_id, distance in zip(row_ids, row_dists):
                other = doc_to_claim.get(doc_id)
                if other is None:
                    stats["unresolved_neighbor_ids"] += 1
                    continue
                if other == cid:
                    stats["self_hits"] += 1
                    continue
                b = by_id[other]
                if not a["arxiv_id"] or not b["arxiv_id"]:
                    stats["missing_arxiv_hits"] += 1
                    continue
                if a["arxiv_id"] == b["arxiv_id"]:
                    stats["same_paper_hits"] += 1
                    continue
                if float(distance) > pool_distance:
                    stats["above_pool_distance_hits"] += 1
                    continue
                pair = (cid, other) if cid <= other else (other, cid)
                old = pairs.get(pair)
                if old is None or float(distance) < old:
                    pairs[pair] = float(distance)
        if stats["claims_queried"] - last_report >= PROGRESS_EVERY or start + batch_size >= len(ids):
            last_report = stats["claims_queried"]
            print(f"[mine:text] retrieval: {stats['claims_queried']}/{len(ids)} claims "
                  f"queried, {len(pairs)} unique cross-paper pairs <= {pool_distance}")

    stats["unique_pairs_within_distance"] = len(pairs)
    return pairs, stats


def filter_pool(pairs: dict, by_id: dict, id_pairs: set, text_pairs: set,
                min_distance: float) -> tuple[dict, dict]:
    """Apply the reviewed-set / duplicate-text / tiny-distance exclusions."""
    counts = {
        "reviewed_by_claim_ids": 0,
        "reviewed_by_text": 0,
        "identical_claim_texts": 0,
        "duplicate_text_pairs": 0,
        "empty_text": 0,
        "distance_below_min": 0,
    }
    pool: dict[tuple[str, str], float] = {}
    seen_text_pairs: set[tuple[str, str]] = set()
    # Closest first, so duplicate text pairs keep their best-scoring instance.
    ordered = sorted(pairs.items(), key=lambda kv: (kv[1], kv[0][0], kv[0][1]))
    for pair, distance in ordered:
        if pair in id_pairs:
            counts["reviewed_by_claim_ids"] += 1
            continue
        a, b = by_id[pair[0]], by_id[pair[1]]
        text_a, text_b = norm_text(a["text"]), norm_text(b["text"])
        if not text_a or not text_b:
            counts["empty_text"] += 1
            continue
        if text_a == text_b:
            counts["identical_claim_texts"] += 1
            continue
        text_pair = tuple(sorted((text_a, text_b)))
        if text_pair in text_pairs:
            counts["reviewed_by_text"] += 1
            continue
        if distance < min_distance:
            counts["distance_below_min"] += 1
            continue
        if text_pair in seen_text_pairs:
            counts["duplicate_text_pairs"] += 1
            continue
        seen_text_pairs.add(text_pair)
        pool[pair] = distance
    counts["total_excluded"] = sum(counts.values())
    return pool, counts


def score_pair(a: dict, b: dict, fa: dict, fb: dict) -> dict:
    """Score one pair with the five independent signals."""
    shared = set(fa["tokens"]) & set(fb["tokens"])
    benchmark_keys = sorted(k for k in shared if k in BENCHMARK_TOKENS)
    model_keys = sorted(k for k in shared if k not in BENCHMARK_TOKENS)

    pos_a, neg_a = fa["positive"], fa["negative"]
    pos_b, neg_b = fb["positive"], fb["negative"]
    polarity_fired = bool((pos_a and neg_b) or (neg_a and pos_b))
    cross_pairs = sorted([f"{p}->{n}" for p in pos_a for n in neg_b]
                         + [f"{n}->{p}" for n in neg_a for p in pos_b])

    numeric: dict = {"fired": False, "shared_token": None, "number_a": None,
                     "number_b": None, "relative_difference": None}
    for key in sorted(shared):
        near_a = _nearest_number(fa, key)
        near_b = _nearest_number(fb, key)
        if near_a is None or near_b is None:
            continue
        rd = relative_difference(near_a[1], near_b[1])
        if rd is None or rd <= REL_DIFF_THRESHOLD:
            continue
        if numeric["relative_difference"] is None or rd > numeric["relative_difference"]:
            numeric = {
                "fired": True,
                "shared_token": fa["tokens"].get(key, key),
                "number_a": near_a[1],
                "number_b": near_b[1],
                "relative_difference": round(rd, 6),
            }

    same_subject = bool(a["subject_key"] and a["subject_key"] == b["subject_key"])
    same_metric = bool(a["metric_key"] and a["metric_key"] == b["metric_key"])
    opposite = (a["sign"] is not None and b["sign"] is not None
                and a["sign"] * b["sign"] == -1)
    structured = {
        "fired": bool(same_subject and same_metric and opposite),
        "same_subject": same_subject,
        "same_metric": same_metric,
        "opposite_direction": opposite,
        "subject": a["subject_key"] if same_subject else None,
        "metric": a["metric_key"] if same_metric else None,
        "direction_a": a["direction"],
        "direction_b": b["direction"],
    }

    signals = {
        "shared_benchmark": {
            "fired": bool(benchmark_keys),
            "tokens": [fa["tokens"].get(k, k) for k in benchmark_keys],
        },
        "shared_model": {
            "fired": bool(model_keys),
            "tokens": [fa["tokens"].get(k, k) for k in model_keys],
        },
        "opposite_polarity": {
            "fired": polarity_fired,
            "positive_a": sorted(pos_a)[:10],
            "negative_a": sorted(neg_a)[:10],
            "positive_b": sorted(pos_b)[:10],
            "negative_b": sorted(neg_b)[:10],
            "cross": cross_pairs[:10],
        },
        "numeric_disagreement": numeric,
        "structured_direction": structured,
    }
    return {
        "signals": signals,
        "score": int(sum(1 for detail in signals.values() if detail["fired"])),
    }


def rank_key(pair: tuple[str, str], scored: dict, distances: dict) -> tuple:
    distance = distances.get(pair)
    return (-scored[pair]["score"],
            distance if distance is not None else float("inf"),
            pair[0], pair[1])


def select_pairs(pool: dict, scored: dict, distances: dict, by_id: dict,
                 cap: int, per_paper_pair: int) -> tuple[list, list, list, int]:
    """Return (ranked, eligible-after-paper-cap, selected, cap skips)."""
    ranked = sorted(pool, key=lambda pair: rank_key(pair, scored, distances))
    counts: Counter = Counter()
    eligible: list[tuple[str, str]] = []
    skipped = 0
    for pair in ranked:
        paper_pair = tuple(sorted((by_id[pair[0]]["arxiv_id"],
                                   by_id[pair[1]]["arxiv_id"])))
        if counts[paper_pair] >= per_paper_pair:
            skipped += 1
            continue
        counts[paper_pair] += 1
        eligible.append(pair)
    return ranked, eligible, eligible[: max(cap, 0)], skipped


def text_sanity_check(df: pd.DataFrame, label_col: str, by_id: dict,
                      features: dict, claim_vec: dict, pool: dict,
                      scored: dict, distances: dict, cap: int) -> list[dict]:
    """Score the reviewed CONTRADICTS pairs separately; rank against the pool."""
    positives = df[df[label_col].astype(str).str.strip().str.upper() == "CONTRADICTS"]
    pool_keys = [rank_key(pair, scored, distances) for pair in pool]
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
            entry.update({"in_live_graph": False,
                          "note": "claim(s) not found in the live graph"})
            results.append(entry)
            continue
        result = score_pair(a, b, features[a_id], features[b_id])
        dist = None
        if a_id in claim_vec and b_id in claim_vec:
            dist = cosine_distance(claim_vec[a_id], claim_vec[b_id])
        pair = (a_id, b_id) if a_id <= b_id else (b_id, a_id)
        key = (-result["score"], dist if dist is not None else float("inf"),
               pair[0], pair[1])
        rank = 1 + sum(1 for other in pool_keys if other < key)
        entry.update({
            "in_live_graph": True,
            "score": result["score"],
            "signals_fired": [name for name, detail in result["signals"].items()
                              if detail["fired"]],
            "signals": result["signals"],
            "cosine_distance": round(dist, 6) if dist is not None else None,
            "rank_among_pool": rank,
            "pool_size": len(pool),
            "would_rank_within_cap_ignoring_paper_pair_cap": rank <= cap,
        })
        results.append(entry)
    return results


def write_text_csv(path: Path, selected: list, by_id: dict,
                   distances: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "pair_id", "claim_id_a", "claim_id_b", "arxiv_id_a", "arxiv_id_b",
            "text_a", "text_b", "section_a", "section_b", "cosine_distance",
            "human_label",
        ])
        for index, pair in enumerate(selected, start=1):
            a, b = by_id[pair[0]], by_id[pair[1]]
            writer.writerow([
                f"cand_{index:04d}", pair[0], pair[1],
                a["arxiv_id"], b["arxiv_id"],
                _WS_RE.sub(" ", a["text"]).strip(),
                _WS_RE.sub(" ", b["text"]).strip(),
                _WS_RE.sub(" ", a["section"]).strip(),
                _WS_RE.sub(" ", b["section"]).strip(),
                f"{distances[pair]:.6f}" if distances.get(pair) is not None else "",
                "",
            ])


def run_text(args) -> int:
    print("=== Axion text-heuristic candidate mining (no LLM calls, no labels) ===")
    print(f"[mine:text] Neo4j: {NEO4J_URI}")

    df, label_col, id_pairs, text_pairs = load_reviewed_pairs()
    print(f"[mine:text] reviewed dataset: {REVIEW_DATASET} "
          f"({len(df)} rows, label column '{label_col}', "
          f"{len(id_pairs)} id-pairs, {len(text_pairs)} text-pairs)")

    claims, by_id, _graph_info = load_graph_claims()

    id_stats = chroma_id_convention_stats()
    if id_stats and "error" not in id_stats:
        print(f"[mine:text] ChromaDB claim-id conventions: {id_stats}")
    else:
        print(f"[mine:text] ChromaDB id-convention probe skipped: {id_stats}")

    col, claim_vec, doc_to_claim, missing, fallback_used, doc_count = \
        load_claim_vectors(claims)
    print(f"[mine:text] embeddings: {len(claim_vec)}/{len(claims)} claims resolved "
          f"({len(missing)} missing, {fallback_used} via legacy-int fallback, "
          f"{doc_count} docs in collection)")
    if missing:
        print(f"[mine:text] claims without a usable embedding are not queried "
              f"(first 5: {missing[:5]})")

    print(f"[mine:text] building pool: top-{args.neighbors} neighbours per claim, "
          f"cross-paper, distance <= {args.pool_distance}")
    raw_pairs, retrieval = build_retrieval_pool(
        claims, claim_vec, doc_to_claim, by_id, col,
        args.pool_distance, args.neighbors)
    print(f"[mine:text] raw pool: {len(raw_pairs)} unique cross-paper pairs "
          f"(from {retrieval['neighbor_slots']} neighbour slots; "
          f"{retrieval['unresolved_neighbor_ids']} unresolved, "
          f"{retrieval['self_hits']} self, {retrieval['same_paper_hits']} same-paper, "
          f"{retrieval['missing_arxiv_hits']} missing arxiv, "
          f"{retrieval['above_pool_distance_hits']} above distance)")

    pool, exclusions = filter_pool(raw_pairs, by_id, id_pairs, text_pairs,
                                   args.min_pair_distance)
    print(f"[mine:text] exclusions: {exclusions['reviewed_by_claim_ids']} already reviewed "
          f"by ids, {exclusions['reviewed_by_text']} already reviewed by text, "
          f"{exclusions['identical_claim_texts']} claims with identical text, "
          f"{exclusions['duplicate_text_pairs']} duplicate text pairs, "
          f"{exclusions['empty_text']} empty text, "
          f"{exclusions['distance_below_min']} distance < {args.min_pair_distance} "
          f"-> pool size {len(pool)}")

    print(f"[mine:text] extracting features for {len(claims)} claims...")
    features: dict[str, dict] = {}
    for index, claim in enumerate(claims, start=1):
        features[claim["claim_id"]] = claim_features(claim["text"])
        if index % PROGRESS_EVERY == 0:
            print(f"[mine:text] features: {index}/{len(claims)} claims")

    scored: dict[tuple[str, str], dict] = {}
    signal_counts: Counter = Counter()
    score_counts: Counter = Counter()
    for index, pair in enumerate(pool, start=1):
        result = score_pair(by_id[pair[0]], by_id[pair[1]],
                            features[pair[0]], features[pair[1]])
        scored[pair] = result
        score_counts[result["score"]] += 1
        for name, detail in result["signals"].items():
            if detail["fired"]:
                signal_counts[name] += 1
        if index % 2000 == 0:
            print(f"[mine:text] scoring: {index}/{len(pool)} pairs")

    distances = pool  # Chroma distance is 1-cosine (verified in Prompt 1)
    ranked, eligible_after_cap, selected, skipped = select_pairs(
        pool, scored, distances, by_id, args.cap, args.per_paper_pair)
    selected_signal_counts: Counter = Counter()
    selected_score_counts: Counter = Counter()
    for pair in selected:
        for name, detail in scored[pair]["signals"].items():
            if detail["fired"]:
                selected_signal_counts[name] += 1
        selected_score_counts[scored[pair]["score"]] += 1

    paper_pairs = {tuple(sorted((by_id[pair[0]]["arxiv_id"],
                                 by_id[pair[1]]["arxiv_id"]))) for pair in selected}
    selected_distances = [distances[pair] for pair in selected]
    distance_stats = dist_stats(selected_distances)

    report = {
        "pool": {
            "size": len(pool),
            "raw_unique_pairs_within_distance": len(raw_pairs),
            "retrieval": retrieval,
            "exclusions": exclusions,
        },
        "signal_counts": {name: signal_counts.get(name, 0) for name in (
            "shared_benchmark", "shared_model", "opposite_polarity",
            "numeric_disagreement", "structured_direction")},
        "score_distribution": {str(score): score_counts.get(score, 0)
                               for score in range(6)},
        "selection": {
            "cap": args.cap,
            "selected": len(selected),
            "per_paper_pair_cap": args.per_paper_pair,
            "skipped_by_paper_pair_cap": skipped,
            "paper_pairs_represented": len(paper_pairs),
            "eligible_after_paper_pair_cap": len(eligible_after_cap),
            "not_selected_beyond_cap": max(len(eligible_after_cap) - len(selected), 0),
            "selected_signal_counts": {
                name: selected_signal_counts.get(name, 0) for name in (
                    "shared_benchmark", "shared_model", "opposite_polarity",
                    "numeric_disagreement", "structured_direction")},
            "selected_score_distribution": {
                str(score): selected_score_counts.get(score, 0)
                for score in range(6)},
            "distance": distance_stats,
        },
        "polarity_words": {
            "positive": sorted(POLARITY_POSITIVE),
            "negative": sorted(POLARITY_NEGATIVE),
        },
        "benchmark_tokens": sorted(BENCHMARK_TOKENS),
        "numeric_window_chars": NUMERIC_WINDOW,
    }

    sanity = text_sanity_check(df, label_col, by_id, features, claim_vec,
                               pool, scored, distances, args.cap)
    report["sanity_check_reviewed_contradicts"] = sanity
    report["sanity_check_note"] = (
        "Only 4 reviewed CONTRADICTS pairs exist; far too few to judge the miner. "
        "These pairs are excluded from the candidate pool and were scored in a "
        "separate pass for a coverage sanity check only."
    )

    print("\n=== Text-heuristic mining report ===")
    print(f"[report] pool size: {len(pool)} unique cross-paper pairs")
    print(f"[report] signal counts (pool): "
          + ", ".join(f"{name}={count}" for name, count in report["signal_counts"].items()))
    print(f"[report] score distribution (pool, 0..5): "
          + ", ".join(f"{score}={count}" for score, count in
                      report["score_distribution"].items()))
    print(f"[report] selected {len(selected)} of {len(ranked)} ranked pairs "
          f"(cap {args.cap}, max {args.per_paper_pair} per paper pair; "
          f"{skipped} skipped by the paper-pair cap)")
    print(f"[report] selected score distribution (0..5): "
          + ", ".join(f"{score}={count}" for score, count in
                      report["selection"]["selected_score_distribution"].items()))
    print(f"[report] selected distance min/median/max: "
          f"{distance_stats['min']}/{distance_stats['median']}/{distance_stats['max']}")
    print(f"[report] polarity positive words ({len(POLARITY_POSITIVE)}): "
          f"{', '.join(sorted(POLARITY_POSITIVE))}")
    print(f"[report] polarity negative words ({len(POLARITY_NEGATIVE)}): "
          f"{', '.join(sorted(POLARITY_NEGATIVE))}")

    print("\n=== Sanity check: reviewed CONTRADICTS pairs scored separately "
          "(excluded from the pool) ===")
    print(f"[mine:text] rows with {label_col} == CONTRADICTS: {len(sanity)}")
    for entry in sanity:
        if not entry.get("in_live_graph"):
            print(f"  pair_id={entry['pair_id']}: {entry.get('note')}")
            continue
        print(f"  pair_id={entry['pair_id']}  score={entry['score']}/5  "
              f"distance={entry['cosine_distance']}  "
              f"rank=#{entry['rank_among_pool']} of {entry['pool_size']}  "
              f"top-{args.cap}={entry['would_rank_within_cap_ignoring_paper_pair_cap']}  "
              f"signals={entry['signals_fired']}")
    print("[report] Only 4 reviewed CONTRADICTS pairs exist; that is far too few "
          "to judge the miner.")

    payload = {
        "meta": {
            "generated_at": date.today().isoformat(),
            "script": "eval/mine_contradiction_candidates.py",
            "mode": "text",
            "model": "none — no LLM calls were made",
            "gate_value": {
                "retrieval_pool_max_cosine_distance": args.pool_distance,
                "min_pair_cosine_distance": args.min_pair_distance,
                "production_gate": "not applied — pool is deliberately wider",
            },
            "prompt_hash": "n/a — no prompt used",
            "dataset": {
                "path": str(REVIEW_DATASET),
                "rows": int(len(df)),
                "label_column": label_col,
                "used_for": ["exclusions", "sanity check only"],
            },
            "graph_claims": len(claims),
            "claims_queried": retrieval["claims_queried"],
            "embedding_coverage": {
                "claims": len(claim_vec),
                "missing": len(missing),
                "legacy_int_fallback_used": fallback_used,
                "docs_in_collection": doc_count,
            },
            "chroma_id_conventions": id_stats,
            "outputs": {
                "review_csv": str(TEXT_OUT_PATH),
                "signals_json": str(TEXT_REPORT_PATH),
            },
        },
        "report": report,
        "signals_by_pair_id": {},
    }

    for index, pair in enumerate(selected, start=1):
        pair_id = f"cand_{index:04d}"
        result = scored[pair]
        payload["signals_by_pair_id"][pair_id] = {
            "signals": result["signals"],
            "score": result["score"],
            "cosine_distance": round(distances[pair], 6),
            "paper_pair": sorted((by_id[pair[0]]["arxiv_id"],
                                  by_id[pair[1]]["arxiv_id"])),
        }

    if not args.dry_run:
        write_text_csv(TEXT_OUT_PATH, selected, by_id, distances)
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        with open(TEXT_REPORT_PATH, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        print(f"\n[mine:text] wrote {TEXT_OUT_PATH} ({len(selected)} data rows)")
        print(f"[mine:text] wrote {TEXT_REPORT_PATH}")
    else:
        print(f"\n[mine:text] dry run: would write {TEXT_OUT_PATH} "
              f"({len(selected)} data rows)")
        print(f"[mine:text] dry run: would write {TEXT_REPORT_PATH}")
    return 0


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(
        description="Mine contradiction candidates (no LLM, no labels).")
    parser.add_argument("--mode", choices=["text", "structured"], default="text",
                        help="text = heuristic retrieval pool (default); "
                             "structured = original Prompt-1 rules")
    parser.add_argument("--cap", type=int, default=DEFAULT_CAP,
                        help=f"max rows written to the review CSV (default {DEFAULT_CAP})")
    parser.add_argument("--dry-run", action="store_true",
                        help="print everything but write no files")
    parser.add_argument("--pool-distance", type=float, default=POOL_DISTANCE,
                        help=f"text mode: max cosine distance for the pool "
                             f"(default {POOL_DISTANCE})")
    parser.add_argument("--min-pair-distance", type=float, default=MIN_PAIR_DISTANCE,
                        help=f"text mode: drop pairs closer than this "
                             f"(default {MIN_PAIR_DISTANCE})")
    parser.add_argument("--per-paper-pair", type=int, default=PER_PAPER_PAIR_CAP,
                        help=f"text mode: max pairs per unordered paper pair "
                             f"(default {PER_PAPER_PAIR_CAP})")
    parser.add_argument("--neighbors", type=int, default=TOP_NEIGHBORS,
                        help=f"text mode: retrieval neighbours per claim "
                             f"(default {TOP_NEIGHBORS})")
    args = parser.parse_args()

    if args.mode == "structured":
        return run_structured(args)
    return run_text(args)


if __name__ == "__main__":
    raise SystemExit(main())
