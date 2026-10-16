# eval/metrics.py
"""
Metric computation for the Axion contradiction-classification evaluation.

Pure functions only — no I/O, no model calls — so this module is trivially
unit-testable offline.
"""
from __future__ import annotations

import math

# Canonical label set. Order is significant: it is the axis order of the
# confusion matrix and the per-class report.
CLASSES = ["CONTRADICTS", "SUPPORTS", "UNRELATED"]


def _require_sklearn():
    try:
        from sklearn.metrics import (  # noqa: F401
            accuracy_score,
            confusion_matrix,
            precision_recall_fscore_support,
        )
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError(
            "scikit-learn is required to compute eval metrics. "
            "Install dev dependencies with: pip install -r requirements-dev.txt"
        ) from exc


def _latency_stats(latencies: list[float]) -> dict:
    if not latencies:
        return {"avg": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0}

    ordered = sorted(latencies)

    def percentile(p: float) -> float:
        # Nearest-rank percentile (no numpy dependency needed).
        if len(ordered) == 1:
            return ordered[0]
        rank = math.ceil(p / 100.0 * len(ordered))
        rank = min(max(rank, 1), len(ordered))
        return ordered[rank - 1]

    return {
        "avg": round(sum(ordered) / len(ordered), 2),
        "p50": round(percentile(50), 2),
        "p95": round(percentile(95), 2),
        "max": round(ordered[-1], 2),
    }


def compute_metrics(
    y_true: list[str],
    y_pred: list[str],
    latencies: list[float] | None = None,
    classes: list[str] | None = None,
) -> dict:
    """
    Compute classification metrics for the relationship task.

    Returns a JSON-serialisable dict:

        {
          "n": int,
          "accuracy": float,
          "precision_macro": float, "recall_macro": float, "f1_macro": float,
          "f1_weighted": float,
          "per_class": {label: {precision, recall, f1, support}},
          "confusion_matrix": {true_label: {pred_label: count}},
          "label_distribution": {"true": {...}, "predicted": {...}},
          "latency_ms": {avg, p50, p95, max}
        }

    Macro metrics are computed over the full `classes` list with
    `zero_division=0`, so a class that never appears still shows up (with a
    support of 0) instead of silently vanishing.
    """
    classes = classes or CLASSES
    latencies = latencies or []

    if not y_true:
        return {
            "n": 0,
            "accuracy": 0.0,
            "precision_macro": 0.0,
            "recall_macro": 0.0,
            "f1_macro": 0.0,
            "f1_weighted": 0.0,
            "per_class": {c: {"precision": 0.0, "recall": 0.0, "f1": 0.0, "support": 0} for c in classes},
            "confusion_matrix": {t: {p: 0 for p in classes} for t in classes},
            "label_distribution": {"true": {}, "predicted": {}},
            "latency_ms": _latency_stats(latencies),
        }

    _require_sklearn()
    from sklearn.metrics import (
        accuracy_score,
        confusion_matrix,
        precision_recall_fscore_support,
    )

    # Metrics are computed over the canonical class list so that a class which
    # never appears in y_true/y_pred is still present in the report.
    present = [c for c in classes]
    prec, rec, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=present, average=None, zero_division=0
    )
    micro_prec, micro_rec, f1_weighted, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=present, average="weighted", zero_division=0
    )
    macro_prec, macro_rec, f1_macro, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=present, average="macro", zero_division=0
    )

    cm = confusion_matrix(y_true, y_pred, labels=present)
    cm_dict = {
        true_label: {pred_label: int(cm[i][j]) for j, pred_label in enumerate(present)}
        for i, true_label in enumerate(present)
    }

    per_class = {
        label: {
            "precision": round(float(prec[i]), 4),
            "recall": round(float(rec[i]), 4),
            "f1": round(float(f1[i]), 4),
            "support": int(support[i]),
        }
        for i, label in enumerate(present)
    }

    true_dist: dict[str, int] = {}
    pred_dist: dict[str, int] = {}
    for label in y_true:
        true_dist[label] = true_dist.get(label, 0) + 1
    for label in y_pred:
        pred_dist[label] = pred_dist.get(label, 0) + 1

    return {
        "n": len(y_true),
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision_macro": round(float(macro_prec), 4),
        "recall_macro": round(float(macro_rec), 4),
        "f1_macro": round(float(f1_macro), 4),
        "f1_weighted": round(float(f1_weighted), 4),
        "per_class": per_class,
        "confusion_matrix": cm_dict,
        "label_distribution": {"true": true_dist, "predicted": pred_dist},
        "latency_ms": _latency_stats(latencies),
    }
