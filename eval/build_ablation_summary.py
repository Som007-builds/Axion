#!/usr/bin/env python
"""Build the launch summary and chart data from the completed ablation report.

This is an offline, deterministic step: it reads the committed report JSON,
the reviewed CSVs, and the resumable cache. It never calls a provider and never
changes labels or cache rows.

Usage:
    python eval/build_ablation_summary.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).resolve().parent
ROOT = EVAL_DIR.parent
DATA_DIR = EVAL_DIR / "Data"
RESULTS_DIR = EVAL_DIR / "results"
REPORT_JSON = RESULTS_DIR / "judge_ablation.json"
CACHE_PATH = RESULTS_DIR / "ablation_cache.jsonl"
SUMMARY_MD = RESULTS_DIR / "ablation_summary.md"
CHART_JSON = RESULTS_DIR / "ablation_chart_data.json"

VARIANTS = ("A", "B", "C", "D")


def load_report() -> dict[str, Any]:
    if not REPORT_JSON.exists():
        raise SystemExit(f"missing report: {REPORT_JSON}")
    report = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    if report.get("meta", {}).get("status") != "complete":
        raise SystemExit("report is not complete; refusing to build the summary")
    missing = [key for key in VARIANTS if key not in report.get("variants", {})]
    if missing:
        raise SystemExit(f"report is missing variants: {', '.join(missing)}")
    return report


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {str(key): ("" if value is None else str(value)) for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]


def load_cache() -> dict[tuple[str, str], dict[str, Any]]:
    entries: dict[tuple[str, str], dict[str, Any]] = {}
    with CACHE_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            entries[(str(row["variant"]), str(row["pair_id"]))] = row
    return entries


def outcome(entry: dict[str, Any]) -> str:
    status = entry.get("status")
    if status == "GATE_DROPPED":
        return "UNRELATED (gate)"
    if entry.get("guard_demoted"):
        return "UNRELATED (guard)"
    if status == "PARSE_FAILURE":
        return "UNRELATED (parse)"
    return str(entry.get("predicted"))


def fmt_prop(value: float | None, ci: list[float] | tuple[float, float] | None) -> str:
    if value is None:
        return "n/a"
    if ci is None:
        return f"{value:.3f}"
    return f"{value:.3f} [{ci[0]:.3f}, {ci[1]:.3f}]"


def config_text(variant: dict[str, Any]) -> str:
    return (
        f"gate {variant['gate']:.2f}; {variant['prompt_kind']} prompt; "
        f"guard {'on' if variant['guard'] else 'off'}; "
        f"{variant['provider']}/{variant['model']}"
    )


def example_outcomes(
    pair_id: str, cache: dict[tuple[str, str], dict[str, Any]]
) -> dict[str, str]:
    return {key: outcome(cache[(key, pair_id)]) for key in VARIANTS}


def pick_examples(
    report: dict[str, Any],
    csv_by_id: dict[str, dict[str, str]],
    cache: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    """Use four data-backed examples; fail loudly if the assumptions drift."""
    selected: list[dict[str, Any]] = []

    def add(
        role: str,
        pair_id: str,
        *,
        expected_label: str,
        expected_outcomes: dict[str, str],
        note: str,
    ) -> None:
        if pair_id not in csv_by_id:
            raise SystemExit(f"example pair {pair_id} is missing from the CSV")
        row = csv_by_id[pair_id]
        if row["label"] != expected_label:
            raise SystemExit(
                f"example pair {pair_id} label changed: {row['label']!r} != {expected_label!r}"
            )
        actual = example_outcomes(pair_id, cache)
        if actual != expected_outcomes:
            raise SystemExit(
                f"example pair {pair_id} outcomes changed: {actual!r} != {expected_outcomes!r}"
            )
        selected.append(
            {
                "role": role,
                "pair_id": pair_id,
                "human_label": expected_label,
                "distance": cache[("A", pair_id)]["distance"],
                "text_a": row["claim_a_text"],
                "text_b": row["claim_b_text"],
                "outcomes": actual,
                "note": note,
            }
        )

    add(
        "a",
        "123",
        expected_label="UNRELATED",
        expected_outcomes={
            "A": "CONTRADICTS",
            "B": "UNRELATED (gate)",
            "C": "UNRELATED (gate)",
            "D": "UNRELATED (gate)",
        },
        note=(
            "A verified false positive that A flags and B/C/D suppress at the 0.35 gate. Both "
            "claims report preserving accuracy while reducing a resource; this is a same-result "
            "restatement, not a contradiction."
        ),
    )
    add(
        "b",
        "171",
        expected_label="UNRELATED",
        expected_outcomes={
            "A": "UNRELATED",
            "B": "CONTRADICTS",
            "C": "UNRELATED",
            "D": "UNRELATED",
        },
        note=(
            "No verified false positive survives all four variants. This is the only verified "
            "false positive still flagged by B; A suppresses it, and C/D suppress all 220."
        ),
    )
    add(
        "c",
        "124",
        expected_label="CONTRADICTS",
        expected_outcomes={
            "A": "CONTRADICTS",
            "B": "UNRELATED (gate)",
            "C": "UNRELATED (gate)",
            "D": "UNRELATED (gate)",
        },
        note=(
            "A confirmed contradiction dropped by the 0.35 gate before judging in B/C/D; A's "
            "0.95 gate keeps it."
        ),
    )
    add(
        "d",
        "215",
        expected_label="CONTRADICTS",
        expected_outcomes={
            "A": "UNRELATED",
            "B": "SUPPORTS",
            "C": "CONTRADICTS",
            "D": "UNRELATED",
        },
        note="C is the only variant that keeps this confirmed contradiction.",
    )
    return selected


def build_summary(report: dict[str, Any], examples: list[dict[str, Any]]) -> str:
    meta = report["meta"]
    variants = report["variants"]
    date = meta.get("date", "")
    lines: list[str] = []
    lines.append(f"# Judge ablation summary — {date}")
    lines.append("")
    lines.append(
        "This summary is generated from `eval/results/judge_ablation.json`; the primary metric "
        "is the 224-row human audit (220 verified false positives, 4 confirmed contradictions). "
        "The full set has 286 reviewed rows."
    )
    lines.append("")
    lines.append("## Headline comparison")
    lines.append("")
    lines.append(
        "| Variant | Configuration | CONTRADICTS flagged | TP | FP | Precision (95% CI) | "
        "TPs kept / 4 | FPs suppressed / 220 |"
    )
    lines.append("|---|---|---:|---:|---:|---|---:|---:|")
    for key in VARIANTS:
        v = variants[key]
        audit = v["audit"]
        lines.append(
            f"| {key} | {config_text(v)} | {v['flagged']} | {v['true_positives']} | "
            f"{v['false_positives']} | {fmt_prop(v['precision'], v.get('precision_ci95'))} | "
            f"{audit['true_positives_kept']}/{audit['confirmed_positives']} | "
            f"{audit['false_positives_stopped']}/{audit['reviewed_false_positives']} |"
        )
    lines.append("")
    lines.append("## What the numbers say")
    lines.append("")
    a = variants["A"]
    b = variants["B"]
    c = variants["C"]
    d = variants["D"]
    lines.append(
        f"- C suppresses all {c['audit']['false_positives_stopped']} verified false positives "
        f"but keeps only {c['audit']['true_positives_kept']}/4 confirmed contradictions; A keeps "
        f"{a['audit']['true_positives_kept']}/4 but leaves {a['audit']['false_positives_remaining']} "
        "verified false positives."
    )
    lines.append(
        f"- B keeps {b['audit']['true_positives_kept']}/4 and D keeps "
        f"{d['audit']['true_positives_kept']}/4 confirmed contradictions. D flags nothing on the "
        "full set, so its precision is undefined; it is an alternative judge, not an assumed upgrade."
    )
    lines.append(
        f"- The 0.35 gate drops pair 124 (distance 0.501931), one of only four confirmed "
        "contradictions, before B/C/D ever judge it; A keeps it."
    )
    sc = report.get("self_consistency") or {}
    lines.append(
        f"- A and B use the same model and old prompt but agree on only "
        f"{sc.get('identical', 0)}/{sc.get('compared', 0)} gate-passing pairs "
        f"({fmt_prop(sc.get('identical_rate'), sc.get('identical_ci95'))}); "
        f"{sc.get('different', 0)} verdicts flip, so a single run is not stable."
    )
    lines.append(
        "- Read this as preliminary pilot evidence: only 4 confirmed positives, one 286-row "
        "reviewed set, 62 rows from unverified negative provenance, and 18/24 pairwise comparisons "
        "within noise. A–C "
        "use the current `openai/gpt-oss-20b`; the original 1.8% production figure came from "
        "`llama-3.1-8b-instant` at gate 0.95 with the old prompt, so the model swap is unmeasured."
    )
    lines.append("")
    lines.append("## Verbatim examples")
    lines.append("")
    lines.append(
        "Claim texts below are copied from `eval/Data/axion_pairs.csv`; pair outcomes are the "
        "final predictions in the cache."
    )
    lines.append("")
    for example in examples:
        role = example["role"]
        lines.append(
            f"### ({role}) Pair `{example['pair_id']}` — human label "
            f"`{example['human_label']}`, distance `{example['distance']:.6f}`"
        )
        lines.append("")
        lines.append(
            "**Variant outcomes:** "
            + "; ".join(
                f"{key} `{example['outcomes'][key]}`" for key in VARIANTS
            )
            + "."
        )
        lines.append("")
        lines.append(f"> Claim A: {example['text_a']}")
        lines.append(">")
        lines.append(f"> Claim B: {example['text_b']}")
        lines.append("")
        lines.append(example["note"])
        lines.append("")
    lines.append("## Read with care")
    lines.append("")
    lines.append(
        "- The audit has only four confirmed positives; precision and recall intervals are wide, "
        "and a one-pair difference can change the ranking."
    )
    lines.append(
        "- The full set includes 62 rows from `labeled_pairs_cleaned` with unverified negative "
        "provenance; the primary audit uses only the 224 human-reviewed rows."
    )
    lines.append(
        "- The pairwise labels are a descriptive Wilson-overlap screen, not a hypothesis test; "
        "18 of 24 comparisons overlap."
    )
    lines.append(
        "- D changes both provider and model, so its result is not a clean estimate of model "
        "strength. A–C's current-model run is not the original production model."
    )
    lines.append("")
    return "\n".join(lines)


def build_chart_data(
    report: dict[str, Any], examples: list[dict[str, Any]]
) -> dict[str, Any]:
    meta = report["meta"]
    variants = report["variants"]
    base_labels = next(
        (d.get("labels", {}) for d in meta.get("datasets", []) if d.get("source_tag") == "base"),
        {},
    )
    audit_labels = meta.get("audit", {}).get("labels", {})
    noise = report.get("noise_comparisons", [])
    sc = report.get("self_consistency") or {}
    gc = report.get("guard_counterfactual") or {}

    variant_rows: list[dict[str, Any]] = []
    for key in VARIANTS:
        v = variants[key]
        audit = v["audit"]
        variant_rows.append(
            {
                "key": key,
                "title": v["title"],
                "configuration": config_text(v),
                "gate": v["gate"],
                "prompt_kind": v["prompt_kind"],
                "guard": v["guard"],
                "provider": v["provider"],
                "model": v["model"],
                "full_set": {
                    "evaluated": v["evaluated"],
                    "total_pairs": v["total_pairs"],
                    "flagged": v["flagged"],
                    "tp": v["true_positives"],
                    "fp": v["false_positives"],
                    "fn": v["false_negatives"],
                    "precision": v["precision"],
                    "precision_ci95": v.get("precision_ci95"),
                    "recall": v["recall"],
                    "recall_ci95": v.get("recall_ci95"),
                    "macro_f1": v["macro_f1"],
                    "llm_calls": v["llm_calls"],
                    "tokens": v["tokens"],
                },
                "audit": {
                    "rows_evaluated": audit["audit_rows_evaluated"],
                    "rows_total": audit["audit_rows_total"],
                    "fp_stopped": audit["false_positives_stopped"],
                    "fp_total": audit["reviewed_false_positives"],
                    "fp_suppression_rate": audit["false_positive_suppression_rate"],
                    "fp_suppression_ci95": audit["false_positive_suppression_ci95"],
                    "tp_kept": audit["true_positives_kept"],
                    "tp_total": audit["confirmed_positives"],
                    "tp_retention_rate": audit["true_positive_retention_rate"],
                    "tp_retention_ci95": audit["true_positive_retention_ci95"],
                },
            }
        )

    return {
        "schema_version": "judge_ablation_chart_data_v1",
        "generated_at": meta.get("generated_at"),
        "date": meta.get("date"),
        "sources": {
            "report": "eval/results/judge_ablation.json",
            "full_set": "eval/Data/axion_pairs.csv",
            "audit": "eval/Data/contradicts_review_labeled.csv",
            "cache": meta.get("cache", {}).get("path", "eval/results/ablation_cache.jsonl"),
        },
        "counts": {
            "full_set_rows": meta.get("full_set_row_count"),
            "full_set_labels": base_labels,
            "audit_rows": meta.get("audit", {}).get("rows_total"),
            "audit_labels": audit_labels,
            "audit_false_positives": meta.get("audit", {}).get("verified_false_positives"),
            "audit_confirmed_positives": meta.get("audit", {}).get("confirmed_positives"),
        },
        "variants": variant_rows,
        "charts": {
            "primary_audit": {
                "labels": list(VARIANTS),
                "fp_stopped": [variants[k]["audit"]["false_positives_stopped"] for k in VARIANTS],
                "fp_total": [variants[k]["audit"]["reviewed_false_positives"] for k in VARIANTS],
                "tp_kept": [variants[k]["audit"]["true_positives_kept"] for k in VARIANTS],
                "tp_total": [variants[k]["audit"]["confirmed_positives"] for k in VARIANTS],
            },
            "full_set": {
                "labels": list(VARIANTS),
                "flagged": [variants[k]["flagged"] for k in VARIANTS],
                "tp": [variants[k]["true_positives"] for k in VARIANTS],
                "fp": [variants[k]["false_positives"] for k in VARIANTS],
                "precision": [variants[k]["precision"] for k in VARIANTS],
                "precision_ci95": [variants[k].get("precision_ci95") for k in VARIANTS],
            },
            "self_consistency": {
                "identical": sc.get("identical"),
                "different": sc.get("different"),
                "compared": sc.get("compared"),
                "identical_rate": sc.get("identical_rate"),
                "identical_ci95": sc.get("identical_ci95"),
            },
        },
        "gate": {
            "value": 0.35,
            "true_positives": report.get("true_positive_gate", []),
        },
        "self_consistency": sc,
        "guard_counterfactual": gc,
        "noise": {
            "within_noise": sum(1 for row in noise if row.get("label") == "within noise"),
            "total": len(noise),
            "comparisons": noise,
        },
        "false_positive_examples": report.get("false_positive_examples", {}),
        "examples": examples,
        "caveats": [
            "Preliminary pilot evidence: only 4 confirmed positives; intervals are wide and the ranking is unstable.",
            "One 286-row reviewed dataset, including 62 rows from unverified negative provenance.",
            "18 of 24 pairwise comparisons are within noise; overlap is descriptive, not a test.",
            "A-C use the current openai/gpt-oss-20b, not the original llama-3.1-8b-instant production model; the model swap is unmeasured.",
            "D changes provider and model; it is an alternative judge, not an assumed upgrade.",
        ],
    }


def main() -> int:
    report = load_report()
    full_rows = load_csv_rows(DATA_DIR / "axion_pairs.csv")
    audit_rows = load_csv_rows(DATA_DIR / "contradicts_review_labeled.csv")
    csv_by_id = {str(row["pair_id"]): row for row in full_rows}
    cache = load_cache()

    if len(full_rows) != report["meta"].get("full_set_row_count"):
        raise SystemExit("full-set row count does not match the report")
    if len(audit_rows) != report["meta"].get("audit", {}).get("rows_total"):
        raise SystemExit("audit row count does not match the report")

    examples = pick_examples(report, csv_by_id, cache)
    SUMMARY_MD.write_text(build_summary(report, examples), encoding="utf-8")
    chart_data = build_chart_data(report, examples)
    CHART_JSON.write_text(
        json.dumps(chart_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"wrote {SUMMARY_MD.relative_to(ROOT)}")
    print(f"wrote {CHART_JSON.relative_to(ROOT)}")
    print(f"examples: {', '.join(example['pair_id'] for example in examples)}")
    print(f"variants: {', '.join(VARIANTS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
