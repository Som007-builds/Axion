"""
Build the production-aligned reference eval set -> eval/Data/axion_pairs.csv

Why this exists
---------------
The old splits (`train.csv`, `val.csv`, `test.csv`) cannot measure current
behaviour: their SUPPORTS/CONTRADICTS rows are almost all *same-paper* pairs,
which `agents.contradiction.check_pair` refuses to score. After the harness's
same-paper exclusion they collapse to 100% UNRELATED, so a majority baseline
"scores" 1.0 accuracy and every real predictor looks broken.

Where the labels come from
--------------------------
`contradicts_review_labeled.csv` is the only genuinely reviewed label set in the
repo: 224 pairs the production agent auto-detected as CONTRADICTS, then a human
audited against the 3-question rubric in `label_contradicts.py` (same topic?
agree? genuinely conflict?). The audit found only **4** true CONTRADICTS
(11 SUPPORTS, 209 UNRELATED) - i.e. the detector's precision on this sample is
~1.8%. Those reviewed labels are treated as ground truth here.

`labeled_pairs_cleaned.csv` (68 cross-paper, all UNRELATED) is added as extra
negatives with a distinct `source` tag, since its provenance is unverified.

Output: one cross-paper CSV with the columns the eval harness expects, so
`python eval/run_eval.py --dataset axion_pairs.csv` works unchanged.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent
OUT_PATH = DATA_DIR / "axion_pairs.csv"

# Claim metadata (arxiv id / title) is scattered across the candidate exports.
META_SOURCES = [
    "candidate_pairs_v2.csv",
    "candidate_pairs.csv",
    "train.csv",
    "val.csv",
    "test.csv",
    "labeled_pairs_cleaned.csv",
]


def _pair_key(a, b) -> str:
    return "|".join(sorted([str(a).strip(), str(b).strip()]))


def _build_claim_lookup() -> dict:
    lookup: dict[str, tuple[str, str]] = {}
    for name in META_SOURCES:
        path = DATA_DIR / name
        if not path.is_file():
            continue
        df = pd.read_csv(path)
        for side in ("a", "b"):
            id_col = f"claim_{side}_id"
            if id_col not in df.columns:
                continue
            arxiv_col = f"claim_{side}_arxiv_id"
            title_col = f"claim_{side}_paper_title"
            arxiv_ids = df[arxiv_col].astype(str).tolist() if arxiv_col in df.columns else [""] * len(df)
            titles = df[title_col].astype(str).tolist() if title_col in df.columns else [""] * len(df)
            for cid, arxiv_id, title in zip(df[id_col], arxiv_ids, titles):
                cid = str(cid)
                if cid and cid not in lookup:
                    lookup[cid] = (str(arxiv_id), str(title))
    return lookup


def build() -> tuple[pd.DataFrame, int]:
    review = pd.read_csv(DATA_DIR / "contradicts_review_labeled.csv").rename(
        columns={
            "claim_id_a": "claim_a_id",
            "claim_id_b": "claim_b_id",
            "text_a": "claim_a_text",
            "text_b": "claim_b_text",
        }
    )
    review["label"] = review["human_label"].astype(str).str.strip().str.upper()
    review["source"] = "contradicts_review"
    review["_priority"] = 0

    cleaned = pd.read_csv(DATA_DIR / "labeled_pairs_cleaned.csv")
    cleaned["label"] = cleaned["label"].astype(str).str.strip().str.upper()
    cleaned["source"] = "labeled_pairs_cleaned"
    cleaned["_priority"] = 1

    cols = ["claim_a_id", "claim_b_id", "claim_a_text", "claim_b_text", "label", "source", "_priority"]
    merged = pd.concat([review[cols], cleaned[cols]], ignore_index=True)
    merged["_key"] = [_pair_key(a, b) for a, b in zip(merged["claim_a_id"], merged["claim_b_id"])]

    before = len(merged)
    merged = (
        merged.sort_values("_priority")
        .drop_duplicates("_key", keep="first")
        .reset_index(drop=True)
    )
    dropped = before - len(merged)

    lookup = _build_claim_lookup()
    merged["claim_a_arxiv_id"] = [lookup.get(str(c), ("", ""))[0] for c in merged["claim_a_id"]]
    merged["claim_b_arxiv_id"] = [lookup.get(str(c), ("", ""))[1] for c in merged["claim_b_id"]]
    merged["claim_a_paper_title"] = [lookup.get(str(c), ("", ""))[1] for c in merged["claim_a_id"]]
    merged["claim_b_paper_title"] = [lookup.get(str(c), ("", ""))[1] for c in merged["claim_b_id"]]

    merged.insert(0, "pair_id", range(len(merged)))
    out = merged[
        [
            "pair_id",
            "claim_a_id",
            "claim_b_id",
            "claim_a_text",
            "claim_b_text",
            "claim_a_arxiv_id",
            "claim_b_arxiv_id",
            "claim_a_paper_title",
            "claim_b_paper_title",
            "label",
            "source",
        ]
    ]
    return out, dropped


if __name__ == "__main__":
    if hasattr(os.sys.stdout, "reconfigure"):
        os.sys.stdout.reconfigure(encoding="utf-8")

    out, dropped = build()
    out.to_csv(OUT_PATH, index=False)

    a = out["claim_a_arxiv_id"].astype(str).str.strip()
    b = out["claim_b_arxiv_id"].astype(str).str.strip()
    same_paper = int(((a == b) & (a != "") & (a != "nan")).sum())

    print(f"Wrote {OUT_PATH} ({len(out)} rows; dropped {dropped} duplicate pairs)")
    print(f"Label mix   : {out['label'].value_counts().to_dict()}")
    print(f"By source   : {out['source'].value_counts().to_dict()}")
    print(f"Same-paper  : {same_paper} (should be 0 - the harness would exclude them)")
