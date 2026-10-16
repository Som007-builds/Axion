# eval/predictors.py
"""
Predictors for the Axion contradiction-classification eval.

Each predictor implements::

    name: str
    def predict(self, row: pandas.Series) -> tuple[str, float, object]
        # -> (predicted_label, latency_ms, raw_output)

The offline predictors (majority / random) exist so the harness — and CI —
can exercise the full pipeline without any Neo4j, ChromaDB or LLM calls. They
also provide honest reference points: a majority baseline makes the class
imbalance visible instead of hiding it behind a single accuracy number.
"""
from __future__ import annotations

import random
import time
from typing import Any

from eval.metrics import CLASSES


def _row_value(row, *names, default=""):
    """Return the first present, non-null value among the candidate columns."""
    for name in names:
        if name in row and row[name] is not None:
            value = row[name]
            # NaN check without importing pandas here.
            if isinstance(value, float) and value != value:
                continue
            return value
    return default


class MajorityPredictor:
    """Always predicts the most common label (UNRELATED for this dataset)."""

    name = "majority"

    def __init__(self, label: str = "UNRELATED"):
        if label not in CLASSES:
            raise ValueError(f"Unknown label: {label!r}")
        self.label = label

    def predict(self, row) -> tuple[str, float, Any]:
        return self.label, 0.0, {"relationship": self.label}


class RandomPredictor:
    """Uniformly random over the label set, with a fixed seed for reproducibility."""

    name = "random"

    def __init__(self, seed: int = 0):
        self._rng = random.Random(seed)

    def predict(self, row) -> tuple[str, float, Any]:
        label = self._rng.choice(CLASSES)
        return label, 0.0, {"relationship": label}


class LLMPredictor:
    """
    Real predictor: delegates to ``agents.contradiction.check_pair``.

    ``check_pair`` returns ``None`` for UNRELATED, same-paper pairs and JSON
    parse failures alike. Same-paper pairs are excluded up front by the dataset
    layer, so here ``None`` is interpreted as the model's UNRELATED decision.

    KNOWN LIMITATION: a parse failure is therefore indistinguishable from a
    genuine UNRELATED verdict. Instrumenting ``check_pair`` to expose that
    distinction is tracked separately (see progress.md, Track D).
    """

    name = "llm"

    def predict(self, row) -> tuple[str, float, Any]:
        from agents.contradiction import check_pair

        claim_a = {
            "id": str(_row_value(row, "claim_a_id", default="")),
            "arxiv_id": str(_row_value(row, "claim_a_arxiv_id", default="")),
            "text": str(_row_value(row, "claim_a_text")),
            "paper_title": str(_row_value(row, "claim_a_paper_title", default="Unknown Title A")),
        }
        claim_b = {
            "id": str(_row_value(row, "claim_b_id", default="")),
            "arxiv_id": str(_row_value(row, "claim_b_arxiv_id", default="")),
            "text": str(_row_value(row, "claim_b_text")),
            "paper_title": str(_row_value(row, "claim_b_paper_title", default="Unknown Title B")),
        }

        start = time.perf_counter()
        raw_result = check_pair(claim_a, claim_b)
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        if not isinstance(raw_result, dict) or "relationship" not in raw_result:
            return "UNRELATED", elapsed_ms, raw_result

        label = str(raw_result["relationship"]).strip().upper()
        if label not in CLASSES:
            label = "UNRELATED"
        return label, elapsed_ms, raw_result


PREDICTORS = {
    "majority": MajorityPredictor,
    "random": RandomPredictor,
    "llm": LLMPredictor,
}


def build_predictor(name: str, **kwargs):
    try:
        factory = PREDICTORS[name]
    except KeyError:
        raise ValueError(
            f"Unknown predictor {name!r}. Choose from {sorted(PREDICTORS)}."
        ) from None
    return factory(**kwargs)
