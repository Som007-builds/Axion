# eval/dataset.py
"""
Dataset loading / preparation for the Axion contradiction-classification eval.

Handles the two path-related footguns in the original scripts:

  1. The data directory is ``eval/Data`` (capital D). Hard-coded lowercase
     ``eval/data`` breaks on case-sensitive filesystems (Linux/CI).
  2. Same-paper claim pairs must be excluded *deterministically* before
     scoring, instead of relying on ``check_pair()`` returning ``None`` (which
     collapses same-paper, UNRELATED and parse-failure into one signal).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from eval.metrics import CLASSES

# Resolve paths relative to this file, never relative to the CWD.
EVAL_DIR = Path(__file__).resolve().parent
DATA_DIR = EVAL_DIR / "Data"

REQUIRED_COLUMNS = {"claim_a_text", "claim_b_text", "label"}


def resolve_dataset(name_or_path: str) -> Path:
    """
    Accept either an absolute/relative path or a bare filename that lives in
    ``eval/Data`` (e.g. ``test.csv``).
    """
    candidate = Path(name_or_path)
    if candidate.is_file():
        return candidate

    in_data = DATA_DIR / name_or_path
    if in_data.is_file():
        return in_data

    raise FileNotFoundError(
        f"Dataset not found: {name_or_path!r} (also checked {in_data})"
    )


def load_pairs(path: str | Path) -> pd.DataFrame:
    """Load a labelled pair CSV and validate that it has the required columns."""
    df = pd.read_csv(path)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")

    # Normalise labels: strip whitespace and upper-case for comparison only.
    df["label"] = df["label"].astype(str).str.strip()

    unknown = sorted({lab for lab in df["label"].unique() if lab.upper() not in CLASSES})
    if unknown:
        raise ValueError(
            f"{path} contains labels outside {CLASSES}: {unknown}"
        )
    df["label"] = df["label"].str.upper()
    return df


def prepare_pairs(
    df: pd.DataFrame, exclude_same_paper: bool = True
) -> tuple[pd.DataFrame, dict]:
    """
    Return (prepared_df, report).

    ``report`` describes what was dropped and why, so the eval output is
    self-documenting rather than silently changing the denominator.
    """
    report = {
        "input_rows": int(len(df)),
        "excluded_same_paper": 0,
        "excluded_same_claim": 0,
        "excluded_rows": int(len(df)),
    }

    work = df

    if exclude_same_paper and {"claim_a_arxiv_id", "claim_b_arxiv_id"} <= set(work.columns):
        a = work["claim_a_arxiv_id"].astype(str).str.strip()
        b = work["claim_b_arxiv_id"].astype(str).str.strip()
        same_paper = (a == b) & (a != "") & (b != "") & (a.str.lower() != "nan")
        report["excluded_same_paper"] = int(same_paper.sum())
        work = work[~same_paper]

    if {"claim_a_id", "claim_b_id"} <= set(work.columns):
        a = work["claim_a_id"].astype(str)
        b = work["claim_b_id"].astype(str)
        same_claim = a == b
        report["excluded_same_claim"] = int(same_claim.sum())
        work = work[~same_claim]

    report["excluded_rows"] = int(len(work))
    return work.reset_index(drop=True), report


def composition(df: pd.DataFrame) -> dict:
    """Class distribution of a prepared dataframe (honest imbalance reporting)."""
    counts = {label: int((df["label"] == label).sum()) for label in CLASSES}
    total = int(len(df))
    return {
        "total": total,
        "counts": counts,
        "fractions": {
            label: round(count / total, 4) if total else 0.0
            for label, count in counts.items()
        },
    }
