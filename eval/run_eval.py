# eval/run_eval.py
"""
Single entry point for the Axion relationship-classification evaluation.

Examples
--------
Offline smoke run (no Neo4j / ChromaDB / LLM needed)::

    python eval/run_eval.py --predictor majority
    python eval/run_eval.py --predictor random --seed 7

Real LLM baseline (needs API keys + network)::

    python eval/run_eval.py --predictor llm --dataset test.csv

The output JSON is written to ``eval/results/<predictor>_<dataset>.json``
unless ``--output`` is given.

Exit codes: 0 = ok, 2 = usage/dataset error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

# Make the repository root importable when this file is run directly.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from eval.dataset import (  # noqa: E402
    composition,
    load_pairs,
    prepare_pairs,
    resolve_dataset,
)
from eval.metrics import compute_metrics  # noqa: E402
from eval.predictors import build_predictor  # noqa: E402

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")


def _rel(path) -> str:
    """Best-effort relative path (falls back to absolute across Windows drives)."""
    try:
        return os.path.relpath(str(path), _REPO_ROOT).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def run(
    dataset: str = "test.csv",
    predictor: str = "majority",
    output: str | None = None,
    limit: int | None = None,
    seed: int = 0,
    exclude_same_paper: bool = True,
    verbose: bool = True,
) -> dict:
    """Run one evaluation and return the results dict (also written to JSON)."""
    path = resolve_dataset(dataset)
    df = load_pairs(path)
    original_composition = composition(df)

    prepared, prep_report = prepare_pairs(df, exclude_same_paper=exclude_same_paper)
    if limit is not None:
        prepared = prepared.head(limit)

    model = build_predictor(predictor, **({"seed": seed} if predictor == "random" else {}))
    predictor_diagnostics = getattr(model, "diagnostics", None)

    y_true: list[str] = []
    y_pred: list[str] = []
    latencies: list[float] = []
    predictions: list[dict] = []

    for idx, row in prepared.iterrows():
        true_label = str(row["label"])
        pred_label, latency_ms, _raw = model.predict(row)

        y_true.append(true_label)
        y_pred.append(pred_label)
        latencies.append(latency_ms)

        predictions.append(
            {
                "pair_id": str(row.get("pair_id", idx)),
                "claim_id_a": str(row.get("claim_a_id", "")),
                "claim_id_b": str(row.get("claim_b_id", "")),
                "true_label": true_label,
                "predicted_label": pred_label,
                "latency_ms": round(latency_ms, 2),
                "matched": pred_label == true_label,
            }
        )

        if verbose:
            print(
                f"[{idx + 1}/{len(prepared)}] true={true_label:<11} "
                f"pred={pred_label:<11} match={pred_label == true_label} "
                f"({latency_ms:.1f} ms)"
            )

    metrics = compute_metrics(y_true, y_pred, latencies)

    warnings = _diagnose(metrics, prep_report, predictor_diagnostics)

    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "path": _rel(path),
            "input_rows": prep_report["input_rows"],
            "evaluated_rows": prep_report["excluded_rows"],
            "excluded_same_paper": prep_report["excluded_same_paper"],
            "excluded_same_claim": prep_report["excluded_same_claim"],
            "limit": limit,
            "composition_before_exclusion": original_composition,
        },
        "predictor": model.name,
        "seed": seed if predictor == "random" else None,
        "warnings": warnings,
        "predictor_diagnostics": predictor_diagnostics,
        "metrics": metrics,
        "predictions": predictions,
    }

    out_path = output or os.path.join(RESULTS_DIR, f"{model.name}_{path.stem}.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)

    if verbose:
        _print_summary(results, out_path)

    return results


def _diagnose(metrics: dict, prep_report: dict, predictor_diagnostics: dict | None = None) -> list[str]:
    """
    Surface conditions that make the headline numbers misleading, instead of
    letting a single accuracy value stand on its own.
    """
    warnings: list[str] = []
    n = metrics["n"]

    if n == 0:
        warnings.append("No pairs were evaluated.")
        return warnings

    evaluated = prep_report["excluded_rows"]
    if prep_report["input_rows"] and evaluated < 0.2 * prep_report["input_rows"]:
        warnings.append(
            f"Only {evaluated}/{prep_report['input_rows']} rows evaluated after "
            "same-paper exclusion — the metric covers a small, unrepresentative slice."
        )

    present_classes = [c for c, d in metrics["per_class"].items() if d["support"] > 0]
    missing_support = [c for c, d in metrics["per_class"].items() if d["support"] == 0]

    if len(present_classes) <= 1:
        warnings.append(
            f"Evaluation is single-class ({present_classes or ['none']}); "
            "accuracy is uninformative. Macro F1 is reported over all classes."
        )
    for label in missing_support:
        warnings.append(f"Class {label} has 0 evaluated examples.")

    if predictor_diagnostics:
        parse_failures = int(predictor_diagnostics.get("parse_failures", 0))
        if parse_failures:
            warnings.append(
                f"{parse_failures} prediction(s) were JSON parse failures and scored as "
                "UNRELATED — treat those as model errors, not genuine negatives."
            )

    return warnings


def _print_summary(results: dict, out_path: str) -> None:
    m = results["metrics"]
    ds = results["dataset"]

    print("\n" + "-" * 60)
    print(f"Predictor : {results['predictor']}")
    print(f"Dataset   : {ds['path']}  (evaluated {ds['evaluated_rows']} of {ds['input_rows']})")
    print(f"Class mix : {ds['composition_before_exclusion']['counts']}")
    if ds["excluded_same_paper"] or ds["excluded_same_claim"]:
        print(
            f"Excluded  : {ds['excluded_same_paper']} same-paper, "
            f"{ds['excluded_same_claim']} same-claim"
        )
    print("-" * 60)
    if m["n"] == 0:
        print("No pairs were evaluated.")
    else:
        print(f"Accuracy    : {m['accuracy']:.4f}")
        print(f"F1 (macro)  : {m['f1_macro']:.4f}")
        print(f"F1 (weighted): {m['f1_weighted']:.4f}")
        print("Per class:")
        for label in ("CONTRADICTS", "SUPPORTS", "UNRELATED"):
            c = m["per_class"][label]
            print(
                f"  {label:<12} P={c['precision']:.3f} R={c['recall']:.3f} "
                f"F1={c['f1']:.3f} support={c['support']}"
            )
        lat = m["latency_ms"]
        print(f"Latency ms  : avg={lat['avg']} p50={lat['p50']} p95={lat['p95']} max={lat['max']}")
    if results.get("predictor_diagnostics"):
        print(f"Diagnostics : {results['predictor_diagnostics']}")
    if results.get("warnings"):
        print("\nWARNINGS:")
        for w in results["warnings"]:
            print(f"  ! {w}")
    print(f"\nWrote {_rel(out_path)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Axion relationship-classification eval")
    parser.add_argument("--dataset", default="test.csv",
                        help="Path or filename inside eval/Data (default: test.csv)")
    parser.add_argument("--predictor", default="majority",
                        choices=["majority", "random", "llm"],
                        help="Predictor to evaluate (default: majority)")
    parser.add_argument("--output", default=None, help="Output JSON path")
    parser.add_argument("--limit", type=int, default=None, help="Evaluate only the first N pairs")
    parser.add_argument("--seed", type=int, default=0, help="Seed for the random predictor")
    parser.add_argument("--include-same-paper", action="store_true",
                        help="Do not exclude same-paper claim pairs")
    args = parser.parse_args(argv)

    try:
        run(
            dataset=args.dataset,
            predictor=args.predictor,
            output=args.output,
            limit=args.limit,
            seed=args.seed,
            exclude_same_paper=not args.include_same_paper,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
