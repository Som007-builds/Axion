#!/usr/bin/env python
"""Judge ablation harness for the Axion contradiction judge.

Runs four variants over the reviewed contradiction pairs:

  A. Old setup: gate 0.95, the pre-change prompt, no demotion guard.
  B. Gate 0.35 with the old prompt: pairs above 0.35 are never judged.
  C. Current production: gate 0.35, current prompt, demotion guard on.
  D. Same as C, but with the stronger model in the configured provider chain.

Distances are computed locally with ``all-MiniLM-L6-v2`` (``1 - cosine``), so
no Neo4j or ChromaDB connection is needed. The harness is deliberately
single-attempt: it does **not** use ``llm.call_llm`` and does **not** retry or
fall back to another provider. A rate-limit/quota error stops the run cleanly,
leaves completed rows in the cache, and exits non-zero.

Resumability
------------
Every completed pair is appended to ``eval/results/ablation_cache.jsonl`` and
keyed by ``(variant, pair_id)``. On restart, entries with the same variant
signature (prompt hash, gate, guard, model) and pair fingerprint (claim text,
label, paper ids) are reused; everything else is recomputed. A pair that is
skipped by the gate is cached too, so it does not need an LLM call on resume.

Human labels
------------
The harness only *reads* labels. It never writes, fills, repairs, or generates
``human_label``. The base file uses ``label``. ``--extra`` accepts another
reviewed CSV whose label column is ``human_label``; rows with an empty label
are ignored. The primary metric uses the human-labeled audit in
``eval/Data/contradicts_review_labeled.csv`` (224 old production CONTRADICTS
auto-detections: 220 verified false positives and 4 confirmed contradictions).

Usage
-----
    python eval/judge_ablation.py --preregister     # header only, no results
    python eval/judge_ablation.py --dry-run
    python eval/judge_ablation.py                    # all variants, full data
    python eval/judge_ablation.py --limit 50         # first 50 combined rows
    python eval/judge_ablation.py --variants C,D     # useful under tight quota
    python eval/judge_ablation.py --extra eval/human_review/<reviewed>.csv

``--dry-run`` prints both a fresh-run plan (ignores the cache) and the calls
remaining with the current cache, so the quota check is explicit. It makes no
provider calls. The markdown report is written to
``eval/results/judge_ablation.md`` and the machine-readable report to
``eval/results/judge_ablation.json`` after a real run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

EVAL_DIR = Path(__file__).resolve().parent
ROOT = EVAL_DIR.parent
DATA_DIR = EVAL_DIR / "Data"
RESULTS_DIR = EVAL_DIR / "results"
CACHE_PATH = RESULTS_DIR / "ablation_cache.jsonl"
REPORT_MD = RESULTS_DIR / "judge_ablation.md"
REPORT_JSON = RESULTS_DIR / "judge_ablation.json"

sys.path.insert(0, str(ROOT))

# Current production prompt / parser / guard. Imported read-only; this harness
# does not modify agents/contradiction.py or config.py.
from agents.contradiction import (
    CONTRADICTION_PROMPT,
    DECOMPOSITION_KEYS,
    STATUS_DEMOTED,
    STATUS_PARSE_FAILURE,
    STATUS_SAME_CLAIM,
    STATUS_SAME_PAPER,
    STATUS_UNRELATED,
    _as_bool,
    _parse_json_object,
)
from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_THINKING_BUDGET,
    GROQ_API_KEY,
    GROQ_MODEL,
)

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
MAX_TOKENS = 1024
PROGRESS_EVERY = 25
CACHE_VERSION = "judge_ablation_v1"
LABELS = ("CONTRADICTS", "SUPPORTS", "UNRELATED")
DATE = datetime.now(timezone.utc).date().isoformat()

# The audit file is the only source for the primary metric. It contains the
# production agent's old CONTRADICTS auto-detections, which a human then
# reviewed. Do not substitute the optional candidate-review file for this.
AUDIT_PATH = DATA_DIR / "contradicts_review_labeled.csv"
OPTIONAL_EXTRA_PATH = EVAL_DIR / "human_review" / "contradiction_candidates_review.csv"
AUDIT_PROVENANCE = (
    "All rows are production-agent CONTRADICTS auto-detections audited against "
    "the rubric in eval/Data/label_contradicts.py; see eval/README.md."
)

# The gate change landed in 82526c3; the prompt rewrite and demotion guard
# landed in 0063b9b. The commit *before* both is 82526c3^ (ffc222a). The
# prompt text is recovered from git at runtime, so it cannot silently drift or
# be invented. See the docstring above.
OLD_PROMPT_COMMIT = "82526c3^"
OLD_PROMPT_COMMIT_FULL = "ffc222a3ce271833c36a5893e7aaae337e9b27b9"
OLD_PROMPT_BLOB = "8dd1d177450921ec4ad051aee3eb840da04b0636"
OLD_GATE = 0.95

# D is the stronger model available in the configured chain: Gemini 3.8 Flash
# against Groq's openai/gpt-oss-20b. Anthropic is not in LLM_PROVIDER_CHAIN.
STRONGER_MODEL_RATIONALE = (
    f"Configured chain is Groq ({GROQ_MODEL}) + Gemini ({GEMINI_MODEL}); "
    "Gemini 3.8 Flash is the stronger/newer of the two. Anthropic is not in "
    "the configured chain."
)


class QuotaStopped(RuntimeError):
    """Rate limit or quota exhausted; stop without retrying."""


class JudgeStopped(RuntimeError):
    """Any other provider error; stop cleanly and leave the pair uncached."""


# ─── Data ────────────────────────────────────────────────────────────────────


@dataclass
class Pair:
    pair_id: str
    source_tag: str
    source_path: str
    claim_id_a: str
    claim_id_b: str
    text_a: str
    text_b: str
    arxiv_a: str
    arxiv_b: str
    paper_a: str
    paper_b: str
    label: str
    pair_key: str = ""
    distance: float | None = None
    fingerprint: str = ""


def _clean(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _clean_id(value: Any) -> str:
    text = _clean(value)
    # CSV round-trips sometimes turn integer ids into "123.0".
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _normalise_text(value: Any) -> str:
    return re.sub(r"\s+", " ", _clean(value)).casefold()


def canonical_pair_key(
    claim_id_a: Any,
    claim_id_b: Any,
    text_a: Any,
    text_b: Any,
) -> str:
    """Return an order-independent identity for a claim pair.

    Claim ids are preferred because they are stable across exports. Text is a
    fallback for review files that lack ids. The key deliberately ignores
    ``pair_id``: two files can number the same pair differently.
    """
    a = _clean_id(claim_id_a)
    b = _clean_id(claim_id_b)
    if a and b:
        return "id:" + "|".join(sorted((a, b)))
    return "text:" + "|".join(sorted((_normalise_text(text_a), _normalise_text(text_b))))


def _column(df: pd.DataFrame, names: tuple[str, ...], what: str, required: bool = True) -> list[str] | None:
    for name in names:
        if name in df.columns:
            return [_clean(v) for v in df[name].tolist()]
    if required:
        raise SystemExit(f"{what}: missing required column (tried {', '.join(names)})")
    return None


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def load_pairs(
    path: Path,
    source_tag: str,
    *,
    label_column: str,
    ignore_empty_labels: bool = False,
) -> tuple[list[Pair], dict[str, Any]]:
    """Load one reviewed CSV with an explicitly named label column.

    ``axion_pairs.csv`` uses ``label``; the audit and optional review files use
    ``human_label``. Extra review rows with an empty ``human_label`` are
    ignored, never guessed or filled. Empty labels in the base or audit files
    are errors.
    """
    path = path.resolve()
    if not path.exists():
        raise SystemExit(f"dataset not found: {path}")

    df = pd.read_csv(path)
    input_rows = len(df)
    if input_rows == 0:
        raise SystemExit(f"dataset is empty: {_rel(path)}")
    if label_column not in df.columns:
        raise SystemExit(
            f"{_rel(path)}: missing required label column `{label_column}` "
            f"(found {', '.join(str(c) for c in df.columns)})"
        )

    pair_ids = _column(df, ("pair_id",), f"{_rel(path)}: pair id")
    ids_a = _column(df, ("claim_a_id", "claim_id_a"), f"{_rel(path)}: claim A id")
    ids_b = _column(df, ("claim_b_id", "claim_id_b"), f"{_rel(path)}: claim B id")
    texts_a = _column(df, ("claim_a_text", "text_a"), f"{_rel(path)}: claim A text")
    texts_b = _column(df, ("claim_b_text", "text_b"), f"{_rel(path)}: claim B text")
    arxiv_a = _column(
        df, ("claim_a_arxiv_id", "arxiv_id_a"), f"{_rel(path)}: claim A arxiv id", required=False
    ) or [""] * len(df)
    arxiv_b = _column(
        df, ("claim_b_arxiv_id", "arxiv_id_b"), f"{_rel(path)}: claim B arxiv id", required=False
    ) or [""] * len(df)
    titles_a = _column(
        df, ("claim_a_paper_title", "paper_title_a"), f"{_rel(path)}: claim A paper title", required=False
    ) or [""] * len(df)
    titles_b = _column(
        df, ("claim_b_paper_title", "paper_title_b"), f"{_rel(path)}: claim B paper title", required=False
    ) or [""] * len(df)
    labels = [_clean(v).upper() for v in df[label_column].tolist()]

    pairs: list[Pair] = []
    ignored_empty = 0
    for i in range(len(df)):
        pair_id = _clean_id(pair_ids[i])
        label = labels[i]
        if not label:
            if ignore_empty_labels:
                ignored_empty += 1
                continue
            raise SystemExit(
                f"{_rel(path)}: row {i + 2} has an empty `{label_column}`; "
                "human labels are never generated or filled in"
            )
        if not pair_id:
            raise SystemExit(f"{_rel(path)}: row {i + 2} has an empty pair_id")
        if not texts_a[i] or not texts_b[i]:
            raise SystemExit(f"{_rel(path)}: pair {pair_id} has an empty claim text")
        if label not in LABELS:
            raise SystemExit(
                f"{_rel(path)}: pair {pair_id} has invalid label {label!r}; "
                f"expected one of {', '.join(LABELS)} (human labels are never generated)"
            )

        paper_a = titles_a[i] or arxiv_a[i] or "unknown paper"
        paper_b = titles_b[i] or arxiv_b[i] or "unknown paper"
        pairs.append(
            Pair(
                pair_id=pair_id,
                source_tag=source_tag,
                source_path=_rel(path),
                claim_id_a=_clean_id(ids_a[i]),
                claim_id_b=_clean_id(ids_b[i]),
                text_a=texts_a[i],
                text_b=texts_b[i],
                arxiv_a=arxiv_a[i],
                arxiv_b=arxiv_b[i],
                paper_a=paper_a,
                paper_b=paper_b,
                label=label,
                pair_key=canonical_pair_key(ids_a[i], ids_b[i], texts_a[i], texts_b[i]),
            )
        )

    if not pairs:
        if ignore_empty_labels:
            return [], {
                "path": _rel(path),
                "rows": 0,
                "input_rows": input_rows,
                "ignored_empty_labels": ignored_empty,
                "label_column": label_column,
                "labels": {},
                "source_tag": source_tag,
            }
        raise SystemExit(f"dataset has no labeled rows: {_rel(path)}")

    meta = {
        "path": _rel(path),
        "rows": len(pairs),
        "input_rows": input_rows,
        "ignored_empty_labels": ignored_empty,
        "label_column": label_column,
        "labels": dict(sorted(Counter(p.label for p in pairs).items())),
        "source_tag": source_tag,
    }
    if "source" in df.columns:
        sources = [_clean(value) for value in df["source"].tolist()]
        meta["source_counts"] = dict(sorted(Counter(value for value in sources if value).items()))
    return pairs, meta


def load_audit(path: Path = AUDIT_PATH) -> tuple[list[Pair], dict[str, Any]]:
    """Load the human-reviewed audit of the old judge's CONTRADICTS flags."""
    pairs, meta = load_pairs(path, "audit", label_column="human_label")
    confirmed = sum(1 for p in pairs if p.label == "CONTRADICTS")
    verified_fps = len(pairs) - confirmed
    meta.update(
        {
            "old_judge_flagged": len(pairs),
            "verified_false_positives": verified_fps,
            "confirmed_positives": confirmed,
            "provenance": AUDIT_PROVENANCE,
        }
    )
    return pairs, meta


def validate_pairs(
    pairs_full: list[Pair],
    audit_pairs: list[Pair],
) -> dict[str, Pair]:
    """Reject duplicate rows and prove the audit is a labeled subset.

    Duplicate detection is order-independent and uses claim ids (or text when
    ids are absent), so reversing a pair or renumbering it cannot make it count
    twice. The audit is not appended to the full set: it is a labeled subset
    used only for the primary metric.
    """
    by_id: dict[str, Pair] = {}
    by_key: dict[str, Pair] = {}
    for pair in pairs_full:
        if pair.pair_id in by_id:
            other = by_id[pair.pair_id]
            raise SystemExit(
                f"duplicate pair_id {pair.pair_id!r} in {other.source_path} and "
                f"{pair.source_path}; the cache key is (variant, pair_id)"
            )
        if pair.pair_key in by_key:
            other = by_key[pair.pair_key]
            raise SystemExit(
                f"the same claim pair appears twice: {other.source_path} pair "
                f"{other.pair_id} and {pair.source_path} pair {pair.pair_id}"
            )
        by_id[pair.pair_id] = pair
        by_key[pair.pair_key] = pair

    audit_ids: dict[str, Pair] = {}
    audit_keys: dict[str, Pair] = {}
    for pair in audit_pairs:
        if pair.pair_id in audit_ids:
            raise SystemExit(f"duplicate audit pair_id {pair.pair_id!r} in {pair.source_path}")
        if pair.pair_key in audit_keys:
            other = audit_keys[pair.pair_key]
            raise SystemExit(
                f"the same audit pair appears twice: {other.pair_id} and {pair.pair_id}"
            )
        audit_ids[pair.pair_id] = pair
        audit_keys[pair.pair_key] = pair

        full = by_key.get(pair.pair_key)
        if full is None:
            raise SystemExit(
                f"audit pair {pair.pair_id} from {pair.source_path} is missing from the "
                "full reviewed set; refusing to compute the primary metric on a subset "
                "that cannot be matched"
            )
        if full.label != pair.label:
            raise SystemExit(
                f"audit pair {pair.pair_id} label {pair.label!r} does not match "
                f"{full.source_path} pair {full.pair_id} label {full.label!r}"
            )
    return by_key


def pair_fingerprint(pair: Pair) -> str:
    """Stable fingerprint of the row's text/labels, independent of pair_id."""
    h = hashlib.sha256()
    for part in (
        pair.claim_id_a,
        pair.claim_id_b,
        pair.text_a,
        pair.text_b,
        pair.arxiv_a,
        pair.arxiv_b,
        pair.paper_a,
        pair.paper_b,
        pair.label,
    ):
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:32]


def add_distances(pairs: list[Pair]) -> None:
    """Compute local MiniLM distances (1 - cosine) for every pair."""
    if not pairs:
        return
    print(f"[distance] loading {EMBEDDING_MODEL} …")
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(EMBEDDING_MODEL)
    texts = list(dict.fromkeys([p.text_a for p in pairs] + [p.text_b for p in pairs]))
    print(f"[distance] encoding {len(texts)} unique claim texts …")
    embeddings = model.encode(
        texts,
        batch_size=64,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    vectors = {text: emb for text, emb in zip(texts, embeddings)}

    for i, pair in enumerate(pairs, 1):
        distance = 1.0 - float(np.dot(vectors[pair.text_a], vectors[pair.text_b]))
        pair.distance = max(0.0, min(2.0, distance))
        pair.fingerprint = pair_fingerprint(pair)
        if i % 500 == 0:
            print(f"[distance] {i}/{len(pairs)} pairs")

    distances = sorted(float(p.distance) for p in pairs if p.distance is not None)
    print(
        "[distance] min/median/max = "
        f"{distances[0]:.6f} / {float(np.median(distances)):.6f} / {distances[-1]:.6f}"
    )


# ─── Prompts / variants ──────────────────────────────────────────────────────


def recover_old_prompt() -> str:
    """Recover the exact pre-change prompt from git history.

    Refuses to continue if the commit or prompt cannot be found. The harness
    never ships an invented historical prompt.
    """
    try:
        raw = subprocess.check_output(
            ["git", "show", f"{OLD_PROMPT_COMMIT}:agents/contradiction.py"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            stderr=subprocess.PIPE,
        )
    except Exception as exc:
        raise SystemExit(
            "Could not recover the old judge prompt from git history "
            f"({OLD_PROMPT_COMMIT}:agents/contradiction.py). "
            f"Refusing to invent it. Details: {exc}"
        ) from exc

    match = re.search(r'CONTRADICTION_PROMPT = """(.*?)"""', raw, re.DOTALL)
    if not match:
        raise SystemExit(
            f"Could not find CONTRADICTION_PROMPT in {OLD_PROMPT_COMMIT}:agents/contradiction.py; "
            "refusing to invent it."
        )
    prompt = match.group(1)
    if "Think carefully" not in prompt or "Return ONLY valid JSON" not in prompt:
        raise SystemExit(
            f"Recovered prompt from {OLD_PROMPT_COMMIT} does not look like the historical judge prompt; "
            "refusing to use it."
        )
    return prompt


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Variant:
    key: str
    title: str
    gate: float
    prompt_kind: str
    prompt: str
    guard: bool
    provider: str
    model: str

    @property
    def prompt_hash(self) -> str:
        return sha256_text(self.prompt)

    @property
    def signature(self) -> str:
        payload = {
            "cache_version": CACHE_VERSION,
            "key": self.key,
            "gate": self.gate,
            "prompt_sha256": self.prompt_hash,
            "guard": self.guard,
            "provider": self.provider,
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "embedding_model": EMBEDDING_MODEL,
        }
        return sha256_text(json.dumps(payload, sort_keys=True))


def build_variants(old_prompt: str) -> dict[str, Variant]:
    variants = [
        Variant(
            key="A",
            title="Old setup",
            gate=OLD_GATE,
            prompt_kind="old",
            prompt=old_prompt,
            guard=False,
            provider="groq",
            model=GROQ_MODEL,
        ),
        Variant(
            key="B",
            title="Gate 0.35 + old prompt",
            gate=0.35,
            prompt_kind="old",
            prompt=old_prompt,
            guard=False,
            provider="groq",
            model=GROQ_MODEL,
        ),
        Variant(
            key="C",
            title="Current production",
            gate=0.35,
            prompt_kind="current",
            prompt=CONTRADICTION_PROMPT,
            guard=True,
            provider="groq",
            model=GROQ_MODEL,
        ),
        Variant(
            key="D",
            title="Current + stronger model",
            gate=0.35,
            prompt_kind="current",
            prompt=CONTRADICTION_PROMPT,
            guard=True,
            provider="gemini",
            model=GEMINI_MODEL,
        ),
    ]
    return {v.key: v for v in variants}


def build_prompt(variant: Variant, pair: Pair) -> str:
    return variant.prompt.format(
        claim_a=pair.text_a,
        paper_a=pair.paper_a,
        claim_b=pair.text_b,
        paper_b=pair.paper_b,
    )


# ─── Provider calls (single attempt, no retries/fallback) ───────────────────


def _is_quota_error(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(exc, "code", None)
    if status == 429:
        return True
    text = f"{type(exc).__name__}: {exc}".lower()
    needles = (
        "ratelimit",
        "rate limit",
        "rate-limit",
        "too many requests",
        "429",
        "quota",
        "resource_exhausted",
        "resource exhausted",
        "insufficient_quota",
        "insufficient quota",
        "billing",
        "credit",
    )
    return any(needle in text for needle in needles)


def _usage_dict(prompt_tokens: Any, completion_tokens: Any, total_tokens: Any) -> dict[str, int | None]:
    def as_int(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    p = as_int(prompt_tokens)
    c = as_int(completion_tokens)
    t = as_int(total_tokens)
    if t is None and p is not None and c is not None:
        t = p + c
    return {"prompt_tokens": p, "completion_tokens": c, "total_tokens": t}


def call_provider(variant: Variant, prompt: str) -> tuple[str, dict[str, int | None]]:
    """Make exactly one provider call. Raises QuotaStopped / JudgeStopped."""
    if variant.provider == "groq":
        if not GROQ_API_KEY:
            raise JudgeStopped("GROQ_API_KEY is not set; cannot run variants A/B/C")
        from groq import Groq

        try:
            client = Groq(api_key=GROQ_API_KEY, max_retries=0, timeout=120)
            kwargs: dict[str, Any] = {
                "model": variant.model,
                "max_tokens": MAX_TOKENS,
                "messages": [{"role": "user", "content": prompt}],
            }
            if "gpt-oss" in variant.model or "qwen3" in variant.model:
                kwargs["reasoning_effort"] = "low"
            response = client.chat.completions.create(**kwargs)
        except Exception as exc:
            if _is_quota_error(exc):
                raise QuotaStopped(f"Groq quota/rate limit: {exc}") from exc
            raise JudgeStopped(f"Groq call failed: {exc}") from exc

        text = (response.choices[0].message.content or "").strip()
        usage = getattr(response, "usage", None)
        return text, _usage_dict(
            getattr(usage, "prompt_tokens", None),
            getattr(usage, "completion_tokens", None),
            getattr(usage, "total_tokens", None),
        )

    if variant.provider == "gemini":
        if not GEMINI_API_KEY:
            raise JudgeStopped("GEMINI_API_KEY is not set; cannot run variant D")
        from google import genai
        from google.genai import types

        try:
            # attempts=1 disables the SDK's default retry loop, which is
            # exactly what we do not want under a daily quota.
            client = genai.Client(
                api_key=GEMINI_API_KEY,
                http_options=types.HttpOptions(
                    retry_options=types.HttpRetryOptions(attempts=1)
                ),
            )
            config_kwargs: dict[str, Any] = {"max_output_tokens": MAX_TOKENS}
            if not variant.model.startswith(("gemini-2.0", "gemini-1.5")):
                config_kwargs["thinking_config"] = types.ThinkingConfig(
                    thinking_budget=GEMINI_THINKING_BUDGET
                )
            response = client.models.generate_content(
                model=variant.model,
                contents=prompt,
                config=types.GenerateContentConfig(**config_kwargs),
            )
        except Exception as exc:
            if _is_quota_error(exc):
                raise QuotaStopped(f"Gemini quota/rate limit: {exc}") from exc
            raise JudgeStopped(f"Gemini call failed: {exc}") from exc

        if not response.text:
            reason = None
            if getattr(response, "candidates", None):
                reason = getattr(response.candidates[0], "finish_reason", None)
            raise JudgeStopped(f"Gemini returned no text (finish_reason={reason})")

        usage = getattr(response, "usage_metadata", None)
        return response.text.strip(), _usage_dict(
            getattr(usage, "prompt_token_count", None),
            getattr(usage, "candidates_token_count", None),
            getattr(usage, "total_token_count", None),
        )

    raise JudgeStopped(f"unknown provider: {variant.provider}")


# ─── Cache ──────────────────────────────────────────────────────────────────


def load_cache() -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, int]]:
    entries: dict[tuple[str, str], dict[str, Any]] = {}
    meta = {"lines": 0, "malformed": 0, "duplicate_keys": 0}
    if not CACHE_PATH.exists():
        return entries, meta

    with CACHE_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            meta["lines"] += 1
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                meta["malformed"] += 1
                continue
            if not isinstance(entry, dict) or "variant" not in entry or "pair_id" not in entry:
                meta["malformed"] += 1
                continue
            key = (str(entry["variant"]), str(entry["pair_id"]))
            if key in entries:
                meta["duplicate_keys"] += 1
            entries[key] = entry
    return entries, meta


def append_cache(entry: dict[str, Any]) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with CACHE_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def cache_entry_valid(entry: dict[str, Any] | None, variant: Variant, pair: Pair) -> bool:
    if not entry:
        return False
    if entry.get("signature") != variant.signature:
        return False
    if entry.get("fingerprint") != pair.fingerprint:
        return False
    required = ("predicted", "status", "gate_passed", "llm_called")
    if any(field not in entry for field in required):
        return False
    try:
        return abs(float(entry.get("distance")) - float(pair.distance)) <= 1e-6
    except (TypeError, ValueError):
        return False


# ─── Judge ──────────────────────────────────────────────────────────────────


def _flag_dict(data: dict[str, Any] | None) -> dict[str, bool]:
    if not isinstance(data, dict):
        return {key: False for key in DECOMPOSITION_KEYS}
    return {key: _as_bool(data.get(key)) for key in DECOMPOSITION_KEYS}


def _base_entry(variant: Variant, pair: Pair) -> dict[str, Any]:
    return {
        "variant": variant.key,
        "variant_title": variant.title,
        "pair_id": pair.pair_id,
        "source_tag": pair.source_tag,
        "source_path": pair.source_path,
        "date": DATE,
        "label": pair.label,
        "distance": round(float(pair.distance), 9) if pair.distance is not None else None,
        "gate": variant.gate,
        "gate_passed": bool(pair.distance is not None and pair.distance <= variant.gate),
        "signature": variant.signature,
        "fingerprint": pair.fingerprint,
        "provider": variant.provider,
        "model": variant.model,
        "prompt_sha256": variant.prompt_hash,
        "guard": variant.guard,
        "llm_called": False,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "raw_response": None,
        "raw_relationship": None,
        "flags": {},
        "confidence": None,
        "explanation": None,
        "guard_demoted": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _entry_without_call(
    variant: Variant,
    pair: Pair,
    status: str,
    predicted: str = STATUS_UNRELATED,
) -> dict[str, Any]:
    entry = _base_entry(variant, pair)
    entry.update({"status": status, "predicted": predicted})
    return entry


def _entry_after_judgment(
    variant: Variant,
    pair: Pair,
    raw: str,
    usage: dict[str, int | None],
) -> dict[str, Any]:
    entry = _base_entry(variant, pair)
    entry.update(
        {
            "llm_called": True,
            "raw_response": raw[:4000],
            "prompt_tokens": usage.get("prompt_tokens") or 0,
            "completion_tokens": usage.get("completion_tokens") or 0,
            "total_tokens": usage.get("total_tokens") or 0,
            "prompt_tokens_available": usage.get("prompt_tokens") is not None,
            "completion_tokens_available": usage.get("completion_tokens") is not None,
            "total_tokens_available": usage.get("total_tokens") is not None,
        }
    )

    data = _parse_json_object(raw)
    flags = _flag_dict(data)
    entry["flags"] = flags

    if not isinstance(data, dict) or "relationship" not in data:
        entry.update(
            {
                "status": STATUS_PARSE_FAILURE,
                "predicted": STATUS_UNRELATED,
                "raw_relationship": "PARSE_FAILURE",
            }
        )
        return entry

    relationship = str(data.get("relationship", "")).strip().upper()
    entry["raw_relationship"] = relationship
    try:
        entry["confidence"] = float(data["confidence"]) if data.get("confidence") is not None else None
    except (TypeError, ValueError):
        entry["confidence"] = None
    if data.get("explanation") is not None:
        entry["explanation"] = str(data["explanation"])[:1000]

    if relationship == STATUS_UNRELATED:
        entry.update({"status": STATUS_UNRELATED, "predicted": STATUS_UNRELATED})
        return entry

    if relationship == "CONTRADICTS":
        if variant.guard and not all(flags.values()):
            entry.update(
                {
                    "status": STATUS_DEMOTED,
                    "predicted": STATUS_UNRELATED,
                    "guard_demoted": True,
                }
            )
            return entry
        entry.update({"status": "CONTRADICTS", "predicted": "CONTRADICTS"})
        return entry

    if relationship == "SUPPORTS":
        entry.update({"status": "SUPPORTS", "predicted": "SUPPORTS"})
        return entry

    entry.update({"status": "UNKNOWN_RELATIONSHIP", "predicted": STATUS_UNRELATED})
    return entry


# ─── Evaluation loop ────────────────────────────────────────────────────────


def _pair_done_stats(
    variants: list[Variant],
    pairs: list[Pair],
    results: dict[tuple[str, str], dict[str, Any]],
    calls_this_run: Counter,
) -> None:
    print("\n=== pairs done per variant ===")
    for variant in variants:
        done = sum(1 for pair in pairs if (variant.key, pair.pair_id) in results)
        judged = sum(
            1
            for pair in pairs
            if (variant.key, pair.pair_id) in results
            and results[(variant.key, pair.pair_id)].get("llm_called")
        )
        print(
            f"  {variant.key}: {done}/{len(pairs)} pairs done; "
            f"{judged} judged calls in results; {calls_this_run.get(variant.key, 0)} calls this run"
        )


# ─── Metrics / report ───────────────────────────────────────────────────────


def wilson_ci(k: int, n: int) -> tuple[float, float] | None:
    if n <= 0:
        return None
    z = 1.959963984540054
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denom
    half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def macro_f1(entries: list[dict[str, Any]]) -> float | None:
    """Unweighted mean F1 over the three canonical labels.

    Classes that never appear still contribute an F1 of zero, matching the
    project's ``eval/metrics.py`` convention.
    """
    y_true = [e["label"] for e in entries]
    y_pred = [e["predicted"] for e in entries]
    if not entries:
        return None
    f1s: list[float] = []
    for cls in LABELS:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == cls and p == cls)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != cls and p == cls)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == cls and p != cls)
        denom = 2 * tp + fp + fn
        f1s.append((2 * tp / denom) if denom else 0.0)
    return sum(f1s) / len(f1s)


def _fmt_prop(value: float | None, ci: tuple[float, float] | None = None) -> str:
    if value is None:
        return "n/a"
    if ci is None:
        return f"{value:.3f}"
    return f"{value:.3f} [{ci[0]:.3f}, {ci[1]:.3f}]"


def _fmt_num(value: float | None, digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _variant_metrics(
    variant: Variant,
    entries: list[dict[str, Any]],
    total_pairs: int,
    calls_this_run: int,
) -> dict[str, Any]:
    y_true = [e["label"] for e in entries]
    y_pred = [e["predicted"] for e in entries]
    positives = sum(1 for label in y_true if label == "CONTRADICTS")
    flagged = sum(1 for pred in y_pred if pred == "CONTRADICTS")
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == "CONTRADICTS" and p == "CONTRADICTS")
    fp = flagged - tp
    fn = positives - tp
    precision = (tp / flagged) if flagged else None
    recall = (tp / positives) if positives else None
    precision_ci = wilson_ci(tp, flagged)
    recall_ci = wilson_ci(tp, positives)
    flagged_rate = (flagged / len(entries)) if entries else None

    gate_dropped_pos = [
        e["pair_id"]
        for e in entries
        if e["label"] == "CONTRADICTS" and e.get("status") == "GATE_DROPPED"
    ]
    guard_demoted_pos = [
        e["pair_id"]
        for e in entries
        if e["label"] == "CONTRADICTS" and e.get("guard_demoted")
    ]
    guard_demoted_all = [e["pair_id"] for e in entries if e.get("guard_demoted")]

    def token_sum(field: str, available_flag: str) -> int | None:
        judged = [e for e in entries if e.get("llm_called")]
        if not judged:
            return 0
        vals = [
            int(e[field])
            for e in judged
            if e.get(available_flag, True)
            and isinstance(e.get(field), (int, float))
            and not isinstance(e.get(field), bool)
        ]
        return sum(vals) if vals else None

    predictions = Counter(y_pred)
    statuses = Counter(e.get("status", "") for e in entries)
    return {
        "variant": variant.key,
        "title": variant.title,
        "gate": variant.gate,
        "prompt_kind": variant.prompt_kind,
        "prompt_sha256": variant.prompt_hash,
        "guard": variant.guard,
        "provider": variant.provider,
        "model": variant.model,
        "total_pairs": total_pairs,
        "evaluated": len(entries),
        "complete": len(entries) == total_pairs,
        "confirmed_positives": positives,
        "positives": positives,
        "flagged": flagged,
        "flagged_rate": flagged_rate,
        "flagged_rate_ci95": wilson_ci(flagged, len(entries)),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": precision,
        "precision_ci95": precision_ci,
        "recall": recall,
        "recall_ci95": recall_ci,
        "macro_f1": macro_f1(entries),
        "gate_dropped_positives": gate_dropped_pos,
        "gate_dropped_positives_ci95": wilson_ci(len(gate_dropped_pos), positives),
        "guard_demoted_positives": guard_demoted_pos,
        "guard_demoted_positives_ci95": wilson_ci(len(guard_demoted_pos), positives),
        "guard_demoted_all": guard_demoted_all,
        "llm_calls": sum(1 for e in entries if e.get("llm_called")),
        "llm_calls_this_run": calls_this_run,
        "tokens": {
            "prompt": token_sum("prompt_tokens", "prompt_tokens_available"),
            "completion": token_sum("completion_tokens", "completion_tokens_available"),
            "total": token_sum("total_tokens", "total_tokens_available"),
        },
        "predictions": dict(sorted(predictions.items())),
        "statuses": dict(sorted(statuses.items())),
    }


def _stop_reason(entry: dict[str, Any]) -> str:
    """Classify why a final prediction is not CONTRADICTS."""
    status = entry.get("status")
    if status == "GATE_DROPPED":
        return "gate"
    if entry.get("guard_demoted"):
        return "guard"
    if status == STATUS_PARSE_FAILURE:
        return "parse"
    if status in (STATUS_SAME_CLAIM, STATUS_SAME_PAPER):
        return "same_claim_or_paper"
    if entry.get("llm_called"):
        return "judge"
    return "other"


def _audit_metrics(
    variant: Variant,
    audit_pairs: list[Pair],
    results: dict[tuple[str, str], dict[str, Any]],
    full_by_key: dict[str, Pair],
) -> dict[str, Any]:
    """Primary metrics on the human-reviewed old-judge CONTRADICTS flags.

    Missing rows (for example a ``--limit`` cut) are reported as missing and
    are never counted as stopped false positives or kept true positives.
    """
    evaluated: list[tuple[Pair, dict[str, Any]]] = []
    missing: list[str] = []
    for audit_pair in audit_pairs:
        full = full_by_key.get(audit_pair.pair_key)
        entry = results.get((variant.key, full.pair_id)) if full is not None else None
        if entry is None:
            missing.append(audit_pair.pair_id)
        else:
            evaluated.append((audit_pair, entry))

    fps = [(pair, entry) for pair, entry in evaluated if pair.label != "CONTRADICTS"]
    tps = [(pair, entry) for pair, entry in evaluated if pair.label == "CONTRADICTS"]
    stopped = [(pair, entry) for pair, entry in fps if entry.get("predicted") != "CONTRADICTS"]
    remaining = [(pair, entry) for pair, entry in fps if entry.get("predicted") == "CONTRADICTS"]
    kept = [(pair, entry) for pair, entry in tps if entry.get("predicted") == "CONTRADICTS"]
    missed = [(pair, entry) for pair, entry in tps if entry.get("predicted") != "CONTRADICTS"]

    stop_counts = Counter(_stop_reason(entry) for _, entry in stopped)
    miss_counts = Counter(_stop_reason(entry) for _, entry in missed)

    reviewed_fps = len(fps)
    confirmed_positives = len(tps)
    fp_rate = (len(stopped) / reviewed_fps) if reviewed_fps else None
    tp_rate = (len(kept) / confirmed_positives) if confirmed_positives else None

    return {
        "variant": variant.key,
        "audit_rows_total": len(audit_pairs),
        "audit_rows_evaluated": len(evaluated),
        "audit_complete": len(evaluated) == len(audit_pairs),
        "evaluated_pair_ids": [pair.pair_id for pair, _ in evaluated],
        "missing_pair_ids": missing,
        "false_positives_in_audit": sum(1 for pair in audit_pairs if pair.label != "CONTRADICTS"),
        "reviewed_false_positives": reviewed_fps,
        "false_positives_stopped": len(stopped),
        "false_positives_remaining": len(remaining),
        "false_positive_suppression_rate": fp_rate,
        "false_positive_suppression_ci95": wilson_ci(len(stopped), reviewed_fps),
        "confirmed_positives_in_audit": sum(1 for pair in audit_pairs if pair.label == "CONTRADICTS"),
        "confirmed_positives": confirmed_positives,
        "true_positives_kept": len(kept),
        "true_positives_missed": len(missed),
        "true_positive_retention_rate": tp_rate,
        "true_positive_retention_ci95": wilson_ci(len(kept), confirmed_positives),
        "false_positive_pairs_stopped": [pair.pair_id for pair, _ in stopped],
        "false_positive_pairs_remaining": [pair.pair_id for pair, _ in remaining],
        "true_positive_pairs_kept": [pair.pair_id for pair, _ in kept],
        "true_positive_pairs_missed": [
            {
                "pair_id": pair.pair_id,
                "distance": full_by_key[pair.pair_key].distance,
                "status": entry.get("status"),
                "predicted": entry.get("predicted"),
            }
            for pair, entry in missed
        ],
        "stops_by_mechanism": dict(sorted(stop_counts.items())),
        "misses_by_mechanism": dict(sorted(miss_counts.items())),
    }


def _noise_comparisons(variant_reports: dict[str, Any]) -> list[dict[str, Any]]:
    """Pairwise comparisons, flagged ``within noise`` when Wilson CIs overlap."""
    keys = [key for key in ("A", "B", "C", "D") if key in variant_reports]

    def audit_metric(report: dict[str, Any], field: str, denominator: str) -> tuple[int, int, float | None, Any]:
        audit = report["audit"]
        return (
            audit[field],
            audit[denominator],
            audit["false_positive_suppression_rate"]
            if field == "false_positives_stopped"
            else audit["true_positive_retention_rate"],
            audit["false_positive_suppression_ci95"]
            if field == "false_positives_stopped"
            else audit["true_positive_retention_ci95"],
        )

    specs = [
        (
            "Verified FP suppression (audit)",
            lambda report: audit_metric(report, "false_positives_stopped", "reviewed_false_positives"),
        ),
        (
            "Verified TP retention (audit)",
            lambda report: audit_metric(report, "true_positives_kept", "confirmed_positives"),
        ),
        (
            "CONTRADICTS precision (full set)",
            lambda report: (
                report["true_positives"],
                report["flagged"],
                report["precision"],
                report.get("precision_ci95"),
            ),
        ),
        (
            "CONTRADICTS recall (full set)",
            lambda report: (
                report["true_positives"],
                report["positives"],
                report["recall"],
                report.get("recall_ci95"),
            ),
        ),
    ]

    comparisons: list[dict[str, Any]] = []
    for metric, getter in specs:
        for i, key_a in enumerate(keys):
            for key_b in keys[i + 1 :]:
                k_a, n_a, rate_a, ci_a = getter(variant_reports[key_a])
                k_b, n_b, rate_b, ci_b = getter(variant_reports[key_b])
                if n_a <= 0 or n_b <= 0 or ci_a is None or ci_b is None:
                    overlap = None
                    label = "n/a"
                else:
                    overlap = not (ci_a[1] < ci_b[0] or ci_b[1] < ci_a[0])
                    label = "within noise" if overlap else "CIs disjoint"
                comparisons.append(
                    {
                        "metric": metric,
                        "variant_a": key_a,
                        "variant_b": key_b,
                        "count_a": k_a,
                        "denominator_a": n_a,
                        "rate_a": rate_a,
                        "ci95_a": ci_a,
                        "count_b": k_b,
                        "denominator_b": n_b,
                        "rate_b": rate_b,
                        "ci95_b": ci_b,
                        "difference": (rate_a - rate_b) if rate_a is not None and rate_b is not None else None,
                        "ci_overlap": overlap,
                        "label": label,
                    }
                )
    return comparisons


def build_meta(
    variants: list[Variant],
    pairs: list[Pair],
    cache_meta: dict[str, int],
    calls_this_run: Counter,
    status: str,
    error: str | None,
    args: argparse.Namespace,
    dataset_meta: list[dict[str, Any]],
    pairs_full: list[Pair],
    old_prompt: str,
    audit_pairs: list[Pair],
    audit_meta: dict[str, Any],
) -> dict[str, Any]:
    evaluated_keys = {pair.pair_key for pair in pairs}
    audit_rows_evaluated = sum(1 for pair in audit_pairs if pair.pair_key in evaluated_keys)
    audit_confirmed = sum(1 for pair in audit_pairs if pair.label == "CONTRADICTS")
    audit_fps = len(audit_pairs) - audit_confirmed
    full_confirmed = sum(1 for pair in pairs_full if pair.label == "CONTRADICTS")
    evaluated_confirmed = sum(1 for pair in pairs if pair.label == "CONTRADICTS")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "date": DATE,
        "status": status,
        "error": error,
        "command": " ".join(sys.argv),
        "limit": args.limit,
        "delay_seconds": args.delay,
        "note": args.note,
        "rendered_from_cache": bool(getattr(args, "report_only", False)),
        "requested_variants": [v.key for v in variants],
        "datasets": dataset_meta,
        "combined_rows": len(pairs_full),
        "evaluated_rows": len(pairs),
        "full_set_row_count": len(pairs_full),
        "positives_in_full": full_confirmed,
        "positives_evaluated": evaluated_confirmed,
        "confirmed_positives": {
            "audit": audit_confirmed,
            "full": full_confirmed,
            "evaluated": evaluated_confirmed,
            "plain": f"{full_confirmed} confirmed human CONTRADICTS labels in the full set; "
            f"{audit_confirmed} in the audit subset",
        },
        "audit": {
            **audit_meta,
            "rows_total": len(audit_pairs),
            "rows_evaluated": audit_rows_evaluated,
            "verified_false_positives": audit_fps,
            "confirmed_positives": audit_confirmed,
            "old_judge_flagged": audit_meta.get("old_judge_flagged", len(audit_pairs)),
            "provenance": audit_meta.get("provenance", AUDIT_PROVENANCE),
        },
        "optional_extra": {
            "declared_path": _rel(OPTIONAL_EXTRA_PATH),
            "exists": OPTIONAL_EXTRA_PATH.exists(),
            "supplied_paths": [
                d["path"] for d in dataset_meta if str(d.get("source_tag", "")).startswith("extra")
            ],
        },
        "preregistration": {
            "header_written_before_results": True,
            "definitions": "judge_ablation_v2",
        },
        "embedding_model": EMBEDDING_MODEL,
        "distance_definition": "1 - cosine similarity, computed locally with sentence-transformers",
        "old_prompt": {
            "source_commit": OLD_PROMPT_COMMIT,
            "resolved_commit": OLD_PROMPT_COMMIT_FULL,
            "blob": OLD_PROMPT_BLOB,
            "sha256": sha256_text(old_prompt),
        },
        "current_prompt": {
            "source": "agents/contradiction.py",
            "sha256": sha256_text(CONTRADICTION_PROMPT),
        },
        "variants": {
            v.key: {
                "title": v.title,
                "gate": v.gate,
                "prompt_kind": v.prompt_kind,
                "prompt_sha256": v.prompt_hash,
                "guard": v.guard,
                "provider": v.provider,
                "model": v.model,
            }
            for v in variants
        },
        "stronger_model_rationale": STRONGER_MODEL_RATIONALE,
        "cache": {
            "path": _rel(CACHE_PATH),
            "lines": cache_meta.get("lines", 0),
            "malformed": cache_meta.get("malformed", 0),
            "duplicate_keys": cache_meta.get("duplicate_keys", 0),
        },
        "calls_this_run": dict(sorted(calls_this_run.items())),
    }


def build_report(
    variants: list[Variant],
    pairs: list[Pair],
    results: dict[tuple[str, str], dict[str, Any]],
    cache_meta: dict[str, int],
    calls_this_run: Counter,
    status: str,
    error: str | None,
    args: argparse.Namespace,
    dataset_meta: list[dict[str, Any]],
    pairs_full: list[Pair],
    old_prompt: str,
    audit_pairs: list[Pair],
    audit_meta: dict[str, Any],
    full_by_key: dict[str, Pair],
) -> dict[str, Any]:
    variant_reports: dict[str, Any] = {}
    for variant in variants:
        entries = [
            results[(variant.key, pair.pair_id)]
            for pair in pairs
            if (variant.key, pair.pair_id) in results
        ]
        report = _variant_metrics(
            variant,
            entries,
            total_pairs=len(pairs),
            calls_this_run=calls_this_run.get(variant.key, 0),
        )
        report["missing_pair_ids"] = [
            pair.pair_id for pair in pairs if (variant.key, pair.pair_id) not in results
        ]
        report["audit"] = _audit_metrics(variant, audit_pairs, results, full_by_key)
        variant_reports[variant.key] = report

    positive_rows: list[dict[str, Any]] = []
    for pair in pairs:
        if pair.label != "CONTRADICTS":
            continue
        row: dict[str, Any] = {
            "pair_id": pair.pair_id,
            "distance": pair.distance,
            "source": pair.source_path,
            "predictions": {},
            "statuses": {},
        }
        for variant in variants:
            entry = results.get((variant.key, pair.pair_id))
            if entry is None:
                row["predictions"][variant.key] = "not run"
                row["statuses"][variant.key] = "not run"
            else:
                row["predictions"][variant.key] = entry.get("predicted")
                row["statuses"][variant.key] = entry.get("status")
        positive_rows.append(row)

    meta = build_meta(
        variants,
        pairs,
        cache_meta,
        calls_this_run,
        status,
        error,
        args,
        dataset_meta,
        pairs_full,
        old_prompt,
        audit_pairs,
        audit_meta,
    )
    return {
        "meta": meta,
        "variants": variant_reports,
        "positive_pairs": positive_rows,
        "noise_comparisons": _noise_comparisons(variant_reports),
    }


def build_preregistration_report(
    variants: list[Variant],
    pairs_full: list[Pair],
    cache_meta: dict[str, int],
    args: argparse.Namespace,
    dataset_meta: list[dict[str, Any]],
    old_prompt: str,
    audit_pairs: list[Pair],
    audit_meta: dict[str, Any],
) -> dict[str, Any]:
    """A report skeleton with metadata and definitions, but no results."""
    meta = build_meta(
        variants,
        pairs_full,
        cache_meta,
        Counter(),
        "preregistered",
        None,
        args,
        dataset_meta,
        pairs_full,
        old_prompt,
        audit_pairs,
        audit_meta,
    )
    meta["limit"] = None
    meta["evaluated_rows"] = 0
    meta["positives_evaluated"] = 0
    meta["audit"]["rows_evaluated"] = 0
    return {
        "meta": meta,
        "variants": {},
        "positive_pairs": [],
        "noise_comparisons": [],
    }


def _md_escape(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def write_outputs(
    variants: list[Variant],
    pairs: list[Pair],
    results: dict[tuple[str, str], dict[str, Any]],
    cache_meta: dict[str, int],
    calls_this_run: Counter,
    status: str,
    error: str | None,
    args: argparse.Namespace,
    dataset_meta: list[dict[str, Any]],
    pairs_full: list[Pair],
    old_prompt: str,
    audit_pairs: list[Pair],
    audit_meta: dict[str, Any],
    full_by_key: dict[str, Pair],
) -> None:
    report = build_report(
        variants,
        pairs,
        results,
        cache_meta,
        calls_this_run,
        status,
        error,
        args,
        dataset_meta,
        pairs_full,
        old_prompt,
        audit_pairs,
        audit_meta,
        full_by_key,
    )
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    REPORT_MD.write_text(render_markdown(report), encoding="utf-8")


def _fmt_count_rate(count: int, denominator: int, ci: Any) -> str:
    if denominator <= 0:
        return f"{count}/0 (n/a)"
    return f"{count}/{denominator} ({_fmt_prop(count / denominator, ci)})"


def _variant_model_line(meta: dict[str, Any]) -> str:
    bits: list[str] = []
    for key in ("A", "B", "C", "D"):
        v = meta["variants"].get(key)
        if not v:
            continue
        bits.append(
            f"{key}: gate {v['gate']:.2f}, {v['prompt_kind']} prompt, "
            f"guard {'on' if v['guard'] else 'off'}, `{v['provider']}/{v['model']}`"
        )
    return "; ".join(bits)


def render_header(report: dict[str, Any]) -> list[str]:
    """Pre-registered metadata, definitions, and table layout.

    This header is written before any result and is reused verbatim when the
    results are appended. Do not move results above it.
    """
    meta = report["meta"]
    lines: list[str] = []
    title = f"# Judge ablation — {meta['date']}"
    if meta.get("status") == "preregistered":
        title += " — pre-registered"
    lines.append(title)
    lines.append("")
    if meta.get("status") == "preregistered":
        lines.append(
            "**Status:** `preregistered`; this file intentionally contains no results. "
            "The definitions and table layouts below were written before this file contained "
            "any results."
        )
    else:
        status_text = str(meta.get("status", "unknown"))
        if (
            meta.get("status") == "complete"
            and meta.get("limit") is not None
            and meta.get("evaluated_rows", 0) < meta.get("combined_rows", 0)
        ):
            status_text += " (limited run)"
        lines.append(
            f"**Run status:** `{status_text}`"
            + (f" — {_md_escape(meta['error'])}" if meta.get("error") else "")
        )
        lines.append(
            "**Pre-registration:** the definitions and table layouts below were written before "
            "results; the results in `## Results` use them unchanged."
        )
    if meta.get("note"):
        lines.append(f"**Note:** {_md_escape(meta['note'])}")
    if meta.get("rendered_from_cache"):
        lines.append("**Rendering:** generated from cache; no provider calls were made in this step.")
    lines.append("")

    dataset_bits = []
    for dataset in meta.get("datasets", []):
        labels = ", ".join(f"{key} {value}" for key, value in dataset.get("labels", {}).items())
        extra = ""
        if dataset.get("ignored_empty_labels"):
            extra = f"; ignored {dataset['ignored_empty_labels']} rows with empty labels"
        dataset_bits.append(f"`{dataset['path']}` ({dataset['rows']} labeled rows: {labels}{extra})")
    lines.append("**Full reviewed set:** " + "; ".join(dataset_bits) + ".")
    base_sources = next(
        (
            dataset.get("source_counts", {})
            for dataset in meta.get("datasets", [])
            if dataset.get("source_tag") == "base"
        ),
        {},
    )
    if base_sources.get("labeled_pairs_cleaned"):
        lines.append(
            "**Full-set caveat:** "
            f"{base_sources['labeled_pairs_cleaned']} rows come from `labeled_pairs_cleaned` "
            "(unverified negative provenance) and affect only the secondary full-set metrics; "
            "the primary audit uses the 224 reviewed rows."
        )
    audit = meta.get("audit", {})
    audit_labels = ", ".join(f"{key} {value}" for key, value in audit.get("labels", {}).items())
    lines.append(
        f"**Audit set (primary metric):** `{audit.get('path', _rel(AUDIT_PATH))}` "
        f"({audit.get('rows_total', audit.get('rows', 0))} rows: {audit_labels}); "
        f"{audit.get('old_judge_flagged', audit.get('rows_total', 0))} old production-agent "
        f"CONTRADICTS auto-detections, {audit.get('verified_false_positives', 0)} verified false "
        f"positives, {audit.get('confirmed_positives', 0)} confirmed contradictions."
    )
    lines.append(
        "**Audit provenance:** "
        + _md_escape(str(audit.get("provenance", AUDIT_PROVENANCE)))
        + " The audit's old judge is the production agent that wrote the original CONTRADICTS "
        "edges, not variant A's pre-change setup."
    )
    confirmed = meta.get("confirmed_positives", {})
    lines.append(
        "**Confirmed human CONTRADICTS labels:** "
        + _md_escape(str(confirmed.get("plain", "n/a")))
        + "; labels were read from the CSVs and never generated or filled in."
    )
    lines.append(f"**Variant models and gates:** {_variant_model_line(meta)}.")
    lines.append(
        f"**Prompt hashes:** old `{meta['old_prompt']['sha256']}`; "
        f"current `{meta['current_prompt']['sha256']}`."
    )
    lines.append(f"**Embedding:** `{meta['embedding_model']}`; distance = {meta['distance_definition']}.")
    lines.append(
        f"**Cache:** `{meta['cache']['path']}` ({meta['cache']['lines']} lines, "
        f"{meta['cache']['malformed']} malformed); resumable and keyed by variant signature and "
        "`(variant, pair_id)`; a run may reuse cached rows and make fewer provider calls."
    )
    optional = meta.get("optional_extra", {})
    supplied = optional.get("supplied_paths", [])
    if supplied:
        optional_text = "supplied: " + ", ".join(f"`{path}`" for path in supplied)
    elif optional.get("exists"):
        optional_text = f"`{optional['declared_path']}` is present but was not supplied with `--extra`"
    else:
        optional_text = (
            f"`{optional.get('declared_path', _rel(OPTIONAL_EXTRA_PATH))}` was not present; "
            "no extra rows were added"
        )
    lines.append(f"**Optional extra:** {optional_text}.")
    if meta.get("limit") is not None:
        lines.append(
            f"**Limit:** first {meta['limit']} combined rows; "
            f"{meta.get('positives_evaluated', 0)} of {meta.get('positives_in_full', 0)} "
            "confirmed contradictions evaluated."
        )
    else:
        lines.append(
            f"**Rows:** {meta.get('full_set_row_count', meta.get('combined_rows', 0))} in the full "
            f"reviewed set; {meta.get('positives_in_full', 0)} confirmed contradictions."
        )
    if meta.get("delay_seconds"):
        lines.append(
            f"**Pacing:** {meta['delay_seconds']:.1f}s before each call; provider fallback and "
            "retries are disabled, so a quota error stops the run."
        )
    lines.append("")

    lines.append("## Pre-registered metric definitions")
    lines.append("")
    lines.append(
        "- **Primary audit metric.** The audit file is fixed before the run. A **verified false "
        "positive** is an audit row whose human label is not `CONTRADICTS`; it is **stopped** when "
        "the variant's final prediction is not `CONTRADICTS`. Gate drops, guard demotions, parse "
        "failures, `SUPPORTS`, and `UNRELATED` all count as stopped. A **confirmed true positive** "
        "is an audit row labeled `CONTRADICTS`; it is **kept** when the final prediction is "
        "`CONTRADICTS`. Missing rows are reported as missing, never as stopped or kept."
    )
    lines.append(
        "- **Primary rates.** False-positive suppression is `stopped / reviewed false positives`; "
        "true-positive retention is `kept / confirmed positives evaluated`. Both use Wilson 95% "
        "confidence intervals. `n/a` means the denominator is zero."
    )
    lines.append(
        "- **Secondary full-set metrics.** On the full reviewed set, `CONTRADICTS` precision is "
        "`TP / (TP + FP)`, recall is `TP / (TP + FN)`, and macro F1 is the unweighted mean of the "
        "three class F1 scores. Precision and recall use Wilson 95% intervals; macro F1 is a point "
        "estimate, not a proportion."
    )
    lines.append(
        "- **Gate-dropped positives.** A confirmed `CONTRADICTS` pair whose local MiniLM distance "
        "is greater than the variant gate, so it never reaches the judge. The count is reported "
        "with `dropped / evaluated positives` and a Wilson 95% interval."
    )
    lines.append(
        "- **Noise rule.** For every pairwise variant comparison, the difference is marked "
        "`within noise` when the two Wilson 95% intervals overlap; otherwise it is marked "
        "`CIs disjoint`. Overlap is a descriptive screen, not a hypothesis test."
    )
    lines.append(
        "- **Calls and tokens.** `LLM calls` counts judged rows represented in the results. Tokens "
        "are the provider-reported prompt, completion, and total usage where available; `n/a` means "
        "the provider did not return usage. Cache reuse makes zero new calls."
    )
    lines.append(
        "- **No generated labels.** Empty `human_label` rows in an extra file are ignored; empty "
        "labels in the base or audit files are errors. The harness never writes or repairs a label."
    )
    lines.append("")
    lines.append("## Pre-registered table layout")
    lines.append("")
    lines.append(
        "- **Primary audit table:** `Variant | Audit rows evaluated | Verified FPs stopped / "
        "reviewed | FP suppression (95% CI) | Verified TPs kept / confirmed | TP retention "
        "(95% CI) | FPs remaining | TPs missed`."
    )
    lines.append(
        "- **Secondary full-set table:** `Variant | Gate | Prompt / guard | Model | Evaluated | "
        "CONTRADICTS flagged | TP | FP | FN | Precision (95% CI) | Recall (95% CI) | Macro F1 | "
        "Gate-dropped positives (rate, 95% CI) | LLM calls | Tokens`."
    )
    lines.append(
        "- **Stop-mechanism table:** `Variant | FPs stopped by gate | by guard | by judge | other | "
        "TPs kept | TPs lost to gate | lost to guard | lost to judge | lost to other`."
    )
    lines.append(
        "- **Pairwise noise table:** `Metric | Comparison | A (95% CI) | B (95% CI) | Difference | "
        "CI overlap | Label`."
    )
    lines.append(
        "- **Known-positives table:** `Pair | Distance |` one column per requested variant, with "
        "`CONTRADICTS`, `SUPPORTS`, `UNRELATED`, `UNRELATED (gate)`, `UNRELATED (guard)`, or "
        "`UNRELATED (parse)`."
    )
    lines.append("")
    return lines


def render_markdown(report: dict[str, Any]) -> str:
    meta = report["meta"]
    variants = report["variants"]
    lines = render_header(report)
    lines.append("## Results")
    lines.append("")

    if meta.get("status") == "preregistered" or not variants:
        lines.append(
            "No results yet. Run `--dry-run` to check quota, then run the same command without "
            "`--dry-run` to fill this section; definitions above must remain unchanged."
        )
        lines.append("")
        return "\n".join(lines)

    lines.append("### Primary: verified false-positive suppression (audit set)")
    lines.append("")
    lines.append(
        "| Variant | Audit rows evaluated | Verified FPs stopped / reviewed | FP suppression "
        "(95% CI) | Verified TPs kept / confirmed | TP retention (95% CI) | FPs remaining | TPs missed |"
    )
    lines.append("|---|---:|---:|---|---:|---|---:|---:|")
    for key in ("A", "B", "C", "D"):
        if key not in variants:
            continue
        audit = variants[key]["audit"]
        evaluated = f"{audit['audit_rows_evaluated']}/{audit['audit_rows_total']}"
        if not audit["audit_complete"]:
            evaluated += " (partial)"
        lines.append(
            f"| {key} | {evaluated} | "
            f"{audit['false_positives_stopped']}/{audit['reviewed_false_positives']} | "
            f"{_fmt_prop(audit['false_positive_suppression_rate'], audit['false_positive_suppression_ci95'])} | "
            f"{audit['true_positives_kept']}/{audit['confirmed_positives']} | "
            f"{_fmt_prop(audit['true_positive_retention_rate'], audit['true_positive_retention_ci95'])} | "
            f"{audit['false_positives_remaining']} | {audit['true_positives_missed']} |"
        )
    lines.append("")
    lines.append(
        "Denominators are the evaluated audit rows; the audit contains "
        f"{meta['audit'].get('verified_false_positives', 0)} verified false positives and "
        f"{meta['audit'].get('confirmed_positives', 0)} confirmed contradictions. "
        "A partial variant does not count unevaluated audit rows as stopped or kept."
    )
    lines.append("")

    lines.append("### Secondary: full reviewed set")
    lines.append("")
    lines.append(
        "| Variant | Gate | Prompt / guard | Model | Evaluated | CONTRADICTS flagged | TP | FP | FN | "
        "Precision (95% CI) | Recall (95% CI) | Macro F1 | Gate-dropped positives (rate, 95% CI) | "
        "LLM calls | Tokens |"
    )
    lines.append("|---|---:|---|---|---:|---:|---:|---:|---:|---|---|---:|---|---:|---:|")
    for key in ("A", "B", "C", "D"):
        if key not in variants:
            continue
        v = variants[key]
        evaluated = f"{v['evaluated']}/{v['total_pairs']}"
        if not v["complete"]:
            evaluated += " (partial)"
        tokens = v["tokens"].get("total")
        lines.append(
            "| {key} | {gate:.2f} | {prompt} / {guard} | {provider}/{model} | {evald} | "
            "{flagged} | {tp} | {fp} | {fn} | {prec} | {rec} | {f1} | {gate_pos} | {calls} | "
            "{tokens} |".format(
                key=key,
                gate=v["gate"],
                prompt="old" if v["prompt_kind"] == "old" else "current",
                guard="on" if v["guard"] else "off",
                provider=v["provider"],
                model=v["model"],
                evald=evaluated,
                flagged=v["flagged"],
                tp=v["true_positives"],
                fp=v["false_positives"],
                fn=v["false_negatives"],
                prec=_fmt_prop(v["precision"], v.get("precision_ci95")),
                rec=_fmt_prop(v["recall"], v.get("recall_ci95")),
                f1=_fmt_num(v["macro_f1"]),
                gate_pos=_fmt_count_rate(
                    len(v["gate_dropped_positives"]),
                    v["positives"],
                    v.get("gate_dropped_positives_ci95"),
                ),
                calls=v["llm_calls"],
                tokens=tokens if tokens is not None else "n/a",
            )
        )
    lines.append("")
    lines.append(
        "The full-set denominators are evaluated rows, so a partial variant is not compared as if "
        "it had seen the whole set. `LLM calls` counts rows represented in the results; "
        "`calls_this_run` in the JSON is zero for a cache-only render."
    )
    lines.append("")

    lines.append("### Stop mechanisms on audit false positives")
    lines.append("")
    lines.append(
        "| Variant | FPs stopped by gate | by guard | by judge | other | TPs kept | "
        "TPs lost to gate | lost to guard | lost to judge | lost to other |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for key in ("A", "B", "C", "D"):
        if key not in variants:
            continue
        audit = variants[key]["audit"]
        stops = audit.get("stops_by_mechanism", {})
        misses = audit.get("misses_by_mechanism", {})

        def mechanism(counts: dict[str, int], name: str) -> int:
            return int(counts.get(name, 0))

        lines.append(
            f"| {key} | {mechanism(stops, 'gate')} | {mechanism(stops, 'guard')} | "
            f"{mechanism(stops, 'judge')} | "
            f"{sum(value for name, value in stops.items() if name not in {'gate', 'guard', 'judge'})} | "
            f"{audit['true_positives_kept']} | {mechanism(misses, 'gate')} | "
            f"{mechanism(misses, 'guard')} | {mechanism(misses, 'judge')} | "
            f"{sum(value for name, value in misses.items() if name not in {'gate', 'guard', 'judge'})} |"
        )
    lines.append("")

    positives = report.get("positive_pairs", [])
    lines.append("### Known human CONTRADICTS pairs")
    lines.append("")
    if positives:
        selected = [k for k in ("A", "B", "C", "D") if k in variants]
        lines.append("| Pair | Distance | " + " | ".join(selected) + " |")
        lines.append("|---|---:|" + "|".join("---" for _ in selected) + "|")
        for row in positives:
            cells = []
            for key in ("A", "B", "C", "D"):
                if key not in variants:
                    continue
                pred = row["predictions"].get(key, "not run")
                status = row["statuses"].get(key, "")
                if status == "GATE_DROPPED":
                    cells.append("UNRELATED (gate)")
                elif status == STATUS_DEMOTED:
                    cells.append("UNRELATED (guard)")
                elif status == STATUS_PARSE_FAILURE:
                    cells.append("UNRELATED (parse)")
                else:
                    cells.append(str(pred))
            lines.append(
                f"| {row['pair_id']} | {row['distance']:.6f} | " + " | ".join(cells) + " |"
            )
    else:
        lines.append("No confirmed `CONTRADICTS` pair was included in the evaluated rows.")
    lines.append("")

    comparisons = report.get("noise_comparisons", [])
    lines.append("### Pairwise differences and noise")
    lines.append("")
    if comparisons:
        lines.append(
            "| Metric | Comparison | A (95% CI) | B (95% CI) | Difference | CI overlap | Label |"
        )
        lines.append("|---|---|---|---|---:|---|---|")
        for row in comparisons:
            rate_a = _fmt_prop(row.get("rate_a"), row.get("ci95_a"))
            rate_b = _fmt_prop(row.get("rate_b"), row.get("ci95_b"))
            difference = row.get("difference")
            diff_text = "n/a" if difference is None else f"{difference:+.3f}"
            overlap = row.get("ci_overlap")
            overlap_text = "n/a" if overlap is None else ("overlap" if overlap else "disjoint")
            lines.append(
                f"| {row['metric']} | {row['variant_a']} vs {row['variant_b']} | "
                f"{rate_a} | {rate_b} | {diff_text} | {overlap_text} | {row['label']} |"
            )
    else:
        lines.append("No pairwise comparison is available.")
    lines.append("")
    lines.append("`within noise` means the two Wilson 95% intervals overlap; this is descriptive, not a test.")
    lines.append("")

    lines.append("### Interpretation")
    lines.append("")
    lines.append(_interpretation(report))
    lines.append("")
    lines.append(
        "Reproduce with the command recorded in `judge_ablation.json`; the cache is `"
        + meta["cache"]["path"]
        + "` and is keyed by `(variant, pair_id)`."
    )
    lines.append("")
    return "\n".join(lines)


def _interpretation(report: dict[str, Any]) -> str:
    """Return exactly three interpretation sentences."""
    meta = report["meta"]
    variants = report["variants"]
    if not variants:
        return "No variant was run, so there is nothing to interpret."

    keys = [key for key in ("A", "B", "C", "D") if key in variants]

    def rank_key(key: str) -> tuple[float, float, float, str]:
        audit = variants[key]["audit"]
        return (
            -(audit["false_positive_suppression_rate"] or 0.0),
            -(audit["true_positive_retention_rate"] or 0.0),
            -(variants[key]["precision"] or 0.0),
            key,
        )

    complete_keys = [
        key for key in keys if variants[key]["audit"].get("audit_complete")
    ] or keys

    def rank_tp(key: str) -> tuple[float, float, str]:
        audit = variants[key]["audit"]
        return (
            -(audit["true_positive_retention_rate"] or 0.0),
            -(audit["false_positive_suppression_rate"] or 0.0),
            key,
        )

    best_key = min(complete_keys, key=rank_key)
    retainer_key = min(complete_keys, key=rank_tp)
    best = variants[best_key]
    audit_best = best["audit"]
    s1 = (
        f"On the {meta['audit'].get('rows_total', 0)}-pair audit, variant {best_key} stopped "
        f"{audit_best['false_positives_stopped']}/{audit_best['reviewed_false_positives']} verified "
        f"false positives (suppression {_fmt_prop(audit_best['false_positive_suppression_rate'], audit_best['false_positive_suppression_ci95'])}) "
        f"while keeping {audit_best['true_positives_kept']}/{audit_best['confirmed_positives']} confirmed "
        f"contradictions (retention {_fmt_prop(audit_best['true_positive_retention_rate'], audit_best['true_positive_retention_ci95'])})"
    )
    if retainer_key != best_key:
        audit_ret = variants[retainer_key]["audit"]
        s1 += (
            f"; variant {retainer_key} kept {audit_ret['true_positives_kept']}/"
            f"{audit_ret['confirmed_positives']} confirmed contradictions while stopping "
            f"{audit_ret['false_positives_stopped']}/{audit_ret['reviewed_false_positives']} verified "
            f"false positives"
        )
    s1 += "."

    focus_key = "C" if "C" in variants else best_key
    focus = variants[focus_key]
    if focus["positives"]:
        s2 = (
            f"On the {meta['evaluated_rows']}-row evaluated full set, variant {focus_key} flagged "
            f"{focus['flagged']} pairs with precision {_fmt_prop(focus['precision'], focus.get('precision_ci95'))} "
            f"and recall {_fmt_prop(focus['recall'], focus.get('recall_ci95'))} (macro F1 "
            f"{_fmt_num(focus['macro_f1'])}), and its {focus['gate']:.2f} gate dropped "
            f"{len(focus['gate_dropped_positives'])}/{focus['positives']} confirmed contradictions before the judge."
        )
    else:
        s2 = (
            f"On the {meta['evaluated_rows']}-row evaluated full set, no confirmed contradiction was "
            f"evaluated, so precision and recall are not estimable and macro F1 is "
            f"{_fmt_num(focus['macro_f1'])}."
        )

    comparisons = report.get("noise_comparisons", [])
    noise_count = sum(1 for row in comparisons if row.get("label") == "within noise")
    partial_bits = [
        f"{key} {value['evaluated']}/{value['total_pairs']}"
        for key, value in variants.items()
        if not value["complete"]
    ]
    partial_text = f"; partial variants: {', '.join(partial_bits)}" if partial_bits else ""
    s3 = (
        f"With only {meta['confirmed_positives'].get('full', 0)} confirmed positives, {noise_count} of "
        f"{len(comparisons)} pairwise metric differences are marked within noise, so these are pilot "
        f"signals rather than a stable ranking{partial_text}."
    )
    return f"{s1} {s2} {s3}"


# ─── Dry run ────────────────────────────────────────────────────────────────


def _estimate_tokens(prompt: str) -> int:
    # Rough planning estimate only; real usage is captured from the provider
    # response in the live run.
    return max(1, math.ceil(len(prompt) / 4.0))


def dry_run(
    variants: list[Variant],
    pairs: list[Pair],
    delay: float,
    audit_pairs: list[Pair] | None = None,
) -> int:
    cache, cache_meta = load_cache()
    evaluated_keys = {pair.pair_key for pair in pairs}
    audit_in_eval = [pair for pair in (audit_pairs or []) if pair.pair_key in evaluated_keys]
    audit_fps = sum(1 for pair in audit_in_eval if pair.label != "CONTRADICTS")
    audit_pos = sum(1 for pair in audit_in_eval if pair.label == "CONTRADICTS")
    audit_total = len(audit_pairs or [])

    print("=== judge ablation dry run (no LLM calls) ===")
    print(f"date: {DATE}")
    print(f"combined rows: {len(pairs)}")
    print(f"cache: {_rel(CACHE_PATH)} ({cache_meta.get('lines', 0)} lines, {len(cache)} keys)")
    print(f"embedding: {EMBEDDING_MODEL} (local, 1 - cosine)")
    print(f"pacing delay before each call: {delay:.1f}s (no retries)")
    if audit_pairs is not None:
        print(
            f"audit: {len(audit_in_eval)}/{audit_total} rows in this evaluated set; "
            f"{audit_fps} verified false positives, {audit_pos} confirmed contradictions"
        )
    print()

    total_fresh_calls = 0
    total_fresh_input = 0
    total_resume_calls = 0
    total_resume_input = 0
    provider_calls: Counter = Counter()
    for variant in variants:
        gate_pass = 0
        gate_drop = 0
        same_skip = 0
        cached = 0
        fresh_calls = 0
        fresh_input = 0
        resume_calls = 0
        resume_input = 0
        gate_drop_pos = 0
        for pair in pairs:
            key = (variant.key, pair.pair_id)
            if pair.claim_id_a and pair.claim_id_a == pair.claim_id_b:
                same_skip += 1
                continue
            if pair.arxiv_a and pair.arxiv_a == pair.arxiv_b:
                same_skip += 1
                continue
            if pair.distance is not None and pair.distance > variant.gate:
                gate_drop += 1
                if pair.label == "CONTRADICTS":
                    gate_drop_pos += 1
                continue
            gate_pass += 1
            prompt_tokens = _estimate_tokens(build_prompt(variant, pair))
            fresh_calls += 1
            fresh_input += prompt_tokens
            if cache_entry_valid(cache.get(key), variant, pair):
                cached += 1
            else:
                resume_calls += 1
                resume_input += prompt_tokens

        total_fresh_calls += fresh_calls
        total_fresh_input += fresh_input
        total_resume_calls += resume_calls
        total_resume_input += resume_input
        provider_calls[variant.provider] += fresh_calls
        print(
            f"Variant {variant.key}: {variant.title}\n"
            f"  gate {variant.gate:.2f} | prompt {variant.prompt_kind} ({variant.prompt_hash[:12]}) | "
            f"guard {'on' if variant.guard else 'off'} | {variant.provider}/{variant.model}\n"
            f"  rows {len(pairs)} | gate pass {gate_pass} | gate drop {gate_drop} | "
            f"same-pair skip {same_skip} | cached {cached}\n"
            f"  fresh-run calls {fresh_calls} | estimated fresh input tokens {fresh_input:,} | "
            f"max fresh output tokens {fresh_calls * MAX_TOKENS:,}\n"
            f"  resume calls with current cache {resume_calls} | estimated resume input tokens {resume_input:,} | "
            f"max resume output tokens {resume_calls * MAX_TOKENS:,}\n"
            f"  gate-dropped positives {gate_drop_pos}"
        )
    print()
    print(f"TOTAL rows per variant: {len(pairs)}")
    print(f"TOTAL fresh-run calls: {total_fresh_calls}")
    print("  by provider: " + ", ".join(f"{k}={v}" for k, v in sorted(provider_calls.items())))
    print(f"TOTAL estimated fresh input tokens: {total_fresh_input:,}")
    print(f"TOTAL max fresh output tokens: {total_fresh_calls * MAX_TOKENS:,} ({MAX_TOKENS}/call)")
    print(f"TOTAL resume calls with current cache: {total_resume_calls}")
    print(f"TOTAL estimated resume input tokens: {total_resume_input:,}")
    print(f"TOTAL max resume output tokens: {total_resume_calls * MAX_TOKENS:,}")
    print(
        "note: token estimates use len(prompt)/4 and are for quota planning only; "
        "the live run records actual usage when the provider returns it."
    )
    print()
    print(
        "quota check: compare this with your provider dashboard. The project previously "
        "measured free-tier caps of roughly 200k tokens/day (Groq) and 20 requests/day "
        "(Gemini 3.8 Flash free tier); your reissued/paid limits may differ."
    )
    print("no LLM calls were made.")
    return 0


# ─── CLI ────────────────────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--extra",
        action="append",
        default=[],
        metavar="CSV",
        help=(
            "additional reviewed CSV whose label column is `human_label`; rows with an "
            "empty label are ignored; may be repeated"
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="evaluate only the first N combined rows (applies after all files are combined)",
    )
    parser.add_argument(
        "--variants",
        default="A,B,C,D",
        metavar="LIST",
        help="comma-separated subset of A,B,C,D (default: all)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="proactive sleep before each LLM call for TPM pacing (default: 0; a 429 still stops the run, no retries)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the call plan and estimates without making any LLM call",
    )
    parser.add_argument(
        "--preregister",
        action="store_true",
        help="write only the pre-registered metadata, definitions, and table layout; makes no calls",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="write the markdown/JSON report from cached results only; never calls an LLM",
    )
    parser.add_argument(
        "--note",
        default="",
        metavar="TEXT",
        help="optional note recorded in the report (for example, why a variant is partial)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.limit is not None and args.limit <= 0:
        raise SystemExit("--limit must be a positive integer")
    if args.delay < 0:
        raise SystemExit("--delay must be >= 0")
    if args.dry_run and args.report_only:
        raise SystemExit("--dry-run and --report-only are mutually exclusive")
    if args.preregister and (args.dry_run or args.report_only):
        raise SystemExit("--preregister cannot be combined with --dry-run or --report-only")
    if args.preregister and args.limit is not None:
        raise SystemExit("--preregister must cover the full reviewed set; remove --limit")

    requested = [part.strip().upper() for part in args.variants.split(",") if part.strip()]
    if not requested:
        raise SystemExit("--variants must contain at least one of A,B,C,D")
    if any(key not in {"A", "B", "C", "D"} for key in requested):
        raise SystemExit("--variants must be a comma-separated subset of A,B,C,D")
    if len(set(requested)) != len(requested):
        raise SystemExit("--variants contains duplicate keys")

    old_prompt = recover_old_prompt()
    all_variants = build_variants(old_prompt)
    variants = [all_variants[key] for key in requested]

    base_path = DATA_DIR / "axion_pairs.csv"
    pairs_full, base_meta = load_pairs(base_path, "base", label_column="label")
    dataset_meta = [base_meta]

    for i, extra in enumerate(args.extra, 1):
        extra_pairs, extra_meta = load_pairs(
            Path(extra),
            f"extra{i}",
            label_column="human_label",
            ignore_empty_labels=True,
        )
        pairs_full.extend(extra_pairs)
        dataset_meta.append(extra_meta)

    audit_pairs, audit_meta = load_audit()
    full_by_key = validate_pairs(pairs_full, audit_pairs)

    pairs = pairs_full[: args.limit] if args.limit is not None else list(pairs_full)
    if args.limit is not None and args.limit < len(pairs_full):
        print(
            f"[data] --limit {args.limit}: evaluating {len(pairs)}/{len(pairs_full)} rows; "
            f"{sum(1 for p in pairs if p.label == 'CONTRADICTS')}/"
            f"{sum(1 for p in pairs_full if p.label == 'CONTRADICTS')} confirmed CONTRADICTS included."
        )

    if args.preregister:
        return write_preregistration(
            variants=variants,
            pairs_full=pairs_full,
            args=args,
            dataset_meta=dataset_meta,
            old_prompt=old_prompt,
            audit_pairs=audit_pairs,
            audit_meta=audit_meta,
        )

    add_distances(pairs)

    if args.dry_run:
        return dry_run(variants, pairs, args.delay, audit_pairs=audit_pairs)
    if args.report_only:
        return report_from_cache(
            variants=variants,
            pairs=pairs,
            args=args,
            dataset_meta=dataset_meta,
            pairs_full=pairs_full,
            old_prompt=old_prompt,
            audit_pairs=audit_pairs,
            audit_meta=audit_meta,
            full_by_key=full_by_key,
        )

    print(
        f"\n=== judge ablation | {DATE} | {len(pairs)} rows | "
        f"{sum(1 for p in pairs if p.label == 'CONTRADICTS')} CONTRADICTS | "
        f"variants {','.join(v.key for v in variants)} ==="
    )
    print(f"old prompt: {OLD_PROMPT_COMMIT} ({sha256_text(old_prompt)[:12]})")
    print(f"current prompt: agents/contradiction.py ({sha256_text(CONTRADICTION_PROMPT)[:12]})")
    print("provider fallback/retries: disabled; one attempt per pair\n")
    return run_eval_with_meta(
        variants=variants,
        pairs=pairs,
        args=args,
        dataset_meta=dataset_meta,
        pairs_full=pairs_full,
        old_prompt=old_prompt,
        audit_pairs=audit_pairs,
        audit_meta=audit_meta,
        full_by_key=full_by_key,
    )


def write_preregistration(
    variants: list[Variant],
    pairs_full: list[Pair],
    args: argparse.Namespace,
    dataset_meta: list[dict[str, Any]],
    old_prompt: str,
    audit_pairs: list[Pair],
    audit_meta: dict[str, Any],
) -> int:
    """Write the header before any results exist. No distances, no LLM calls."""
    if REPORT_JSON.exists():
        raise SystemExit(
            f"{_rel(REPORT_JSON)} already exists; archive the prior results before "
            "writing a new pre-registration"
        )
    cache_meta = load_cache()[1]
    report = build_preregistration_report(
        variants=variants,
        pairs_full=pairs_full,
        cache_meta=cache_meta,
        args=args,
        dataset_meta=dataset_meta,
        old_prompt=old_prompt,
        audit_pairs=audit_pairs,
        audit_meta=audit_meta,
    )
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text(render_markdown(report), encoding="utf-8")
    print(
        f"wrote pre-registration header to {_rel(REPORT_MD)}; "
        "no distances computed and no LLM calls made"
    )
    print(
        f"audit: {len(audit_pairs)} rows; "
        f"{audit_meta.get('verified_false_positives', 0)} verified false positives; "
        f"{audit_meta.get('confirmed_positives', 0)} confirmed contradictions"
    )
    return 0


def report_from_cache(
    variants: list[Variant],
    pairs: list[Pair],
    args: argparse.Namespace,
    dataset_meta: list[dict[str, Any]],
    pairs_full: list[Pair],
    old_prompt: str,
    audit_pairs: list[Pair],
    audit_meta: dict[str, Any],
    full_by_key: dict[str, Pair],
) -> int:
    """Write the report from valid cache entries only; make no provider calls."""
    cache, cache_meta = load_cache()
    results: dict[tuple[str, str], dict[str, Any]] = {}
    for variant in variants:
        for pair in pairs:
            entry = cache.get((variant.key, pair.pair_id))
            if cache_entry_valid(entry, variant, pair):
                results[(variant.key, pair.pair_id)] = entry  # type: ignore[assignment]

    _pair_done_stats(variants, pairs, results, Counter())
    missing = [
        f"{variant.key} {sum(1 for pair in pairs if (variant.key, pair.pair_id) in results)}/{len(pairs)}"
        for variant in variants
        if sum(1 for pair in pairs if (variant.key, pair.pair_id) in results) < len(pairs)
    ]
    status = "partial" if missing else "complete"
    write_outputs(
        variants=variants,
        pairs=pairs,
        results=results,
        cache_meta=cache_meta,
        calls_this_run=Counter(),
        status=status,
        error=None,
        args=args,
        dataset_meta=dataset_meta,
        pairs_full=pairs_full,
        old_prompt=old_prompt,
        audit_pairs=audit_pairs,
        audit_meta=audit_meta,
        full_by_key=full_by_key,
    )
    print(f"\nwrote {_rel(REPORT_MD)} and {_rel(REPORT_JSON)} from cache; no LLM calls made")
    return 0


def run_eval_with_meta(
    variants: list[Variant],
    pairs: list[Pair],
    args: argparse.Namespace,
    dataset_meta: list[dict[str, Any]],
    pairs_full: list[Pair],
    old_prompt: str,
    audit_pairs: list[Pair],
    audit_meta: dict[str, Any],
    full_by_key: dict[str, Pair],
) -> int:
    """Run the evaluation, then write the report with full dataset metadata."""
    cache, cache_meta = load_cache()
    results: dict[tuple[str, str], dict[str, Any]] = {}
    calls_this_run: Counter = Counter()
    status = "complete"
    error: str | None = None
    started = time.time()

    try:
        for variant in variants:
            print(f"\n=== Variant {variant.key}: {variant.title} ===")
            print(
                f"gate {variant.gate:.2f} | prompt {variant.prompt_kind} "
                f"({variant.prompt_hash[:12]}) | guard {'on' if variant.guard else 'off'} | "
                f"{variant.provider}/{variant.model}"
            )
            calls = 0
            reused = 0
            for idx, pair in enumerate(pairs, 1):
                key = (variant.key, pair.pair_id)
                cached = cache.get(key)
                if cache_entry_valid(cached, variant, pair):
                    results[key] = cached  # type: ignore[assignment]
                    reused += 1
                else:
                    if pair.claim_id_a and pair.claim_id_a == pair.claim_id_b:
                        entry = _entry_without_call(variant, pair, STATUS_SAME_CLAIM)
                    elif pair.arxiv_a and pair.arxiv_a == pair.arxiv_b:
                        entry = _entry_without_call(variant, pair, STATUS_SAME_PAPER)
                    elif pair.distance is not None and pair.distance > variant.gate:
                        entry = _entry_without_call(variant, pair, "GATE_DROPPED")
                    else:
                        if args.delay > 0:
                            time.sleep(args.delay)
                        prompt = build_prompt(variant, pair)
                        raw, usage = call_provider(variant, prompt)
                        entry = _entry_after_judgment(variant, pair, raw, usage)
                        calls += 1
                        calls_this_run[variant.key] += 1

                    append_cache(entry)
                    cache[key] = entry
                    results[key] = entry

                if idx % PROGRESS_EVERY == 0:
                    elapsed = time.time() - started
                    print(
                        f"  [{variant.key}] {idx}/{len(pairs)} pairs | "
                        f"{calls} calls this variant | {reused} reused | {elapsed:.1f}s"
                    )

            print(
                f"[{variant.key}] done: {len(pairs)}/{len(pairs)} pairs, "
                f"{calls} calls this variant, {reused} reused from cache"
            )

    except QuotaStopped as exc:
        status = "stopped_quota"
        error = str(exc)
        print(f"\n[STOP] quota/rate limit: {error}")
    except JudgeStopped as exc:
        status = "stopped_error"
        error = str(exc)
        print(f"\n[STOP] provider error: {error}")
    except KeyboardInterrupt:
        status = "stopped_interrupt"
        error = "KeyboardInterrupt"
        print("\n[STOP] interrupted")
    except Exception as exc:  # noqa: BLE001
        status = "stopped_error"
        error = f"{type(exc).__name__}: {exc}"
        print(f"\n[STOP] unexpected error: {error}")

    _pair_done_stats(variants, pairs, results, calls_this_run)
    write_outputs(
        variants=variants,
        pairs=pairs,
        results=results,
        cache_meta=cache_meta,
        calls_this_run=calls_this_run,
        status=status,
        error=error,
        args=args,
        dataset_meta=dataset_meta,
        pairs_full=pairs_full,
        old_prompt=old_prompt,
        audit_pairs=audit_pairs,
        audit_meta=audit_meta,
        full_by_key=full_by_key,
    )

    if status == "complete":
        print(f"\nwrote {_rel(REPORT_MD)} and {_rel(REPORT_JSON)}")
        return 0
    code = 2 if status == "stopped_quota" else (130 if status == "stopped_interrupt" else 1)
    print(f"\nrun incomplete ({status}); resume with the same command. exit {code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
