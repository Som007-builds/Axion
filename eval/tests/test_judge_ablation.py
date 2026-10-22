"""Offline unit tests for the judge-ablation harness.

These tests never call a provider and never read the production cache. Run with:

    pytest -q eval/tests/test_judge_ablation.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.judge_ablation import (
    Pair,
    Variant,
    _audit_metrics,
    _interpretation,
    _noise_comparisons,
    _variant_metrics,
    build_preregistration_report,
    canonical_pair_key,
    load_pairs,
    render_markdown,
    validate_pairs,
    wilson_ci,
)


def make_pair(
    pair_id: str,
    label: str,
    *,
    claim_id_a: str | None = None,
    claim_id_b: str | None = None,
    text_a: str = "claim a",
    text_b: str = "claim b",
    distance: float = 0.2,
) -> Pair:
    claim_id_a = claim_id_a or f"claim-{pair_id}-a"
    claim_id_b = claim_id_b or f"claim-{pair_id}-b"
    return Pair(
        pair_id=pair_id,
        source_tag="test",
        source_path="test.csv",
        claim_id_a=claim_id_a,
        claim_id_b=claim_id_b,
        text_a=text_a,
        text_b=text_b,
        arxiv_a="",
        arxiv_b="",
        paper_a="paper a",
        paper_b="paper b",
        label=label,
        pair_key=canonical_pair_key(claim_id_a, claim_id_b, text_a, text_b),
        distance=distance,
        fingerprint=f"fingerprint-{pair_id}",
    )


def make_entry(
    pair: Pair,
    predicted: str,
    *,
    status: str,
    llm_called: bool = True,
    guard_demoted: bool = False,
) -> dict:
    return {
        "pair_id": pair.pair_id,
        "label": pair.label,
        "predicted": predicted,
        "status": status,
        "llm_called": llm_called,
        "guard_demoted": guard_demoted,
        "distance": pair.distance,
    }


def test_load_base_and_extra_label_columns(tmp_path: Path) -> None:
    base = tmp_path / "base.csv"
    pd.DataFrame(
        [
            {
                "pair_id": 1,
                "claim_a_id": "a",
                "claim_b_id": "b",
                "claim_a_text": "A",
                "claim_b_text": "B",
                "label": "CONTRADICTS",
            }
        ]
    ).to_csv(base, index=False)

    pairs, meta = load_pairs(base, "base", label_column="label")
    assert len(pairs) == 1
    assert pairs[0].label == "CONTRADICTS"
    assert meta["label_column"] == "label"

    extra = tmp_path / "extra.csv"
    pd.DataFrame(
        [
            {
                "pair_id": "cand_1",
                "claim_id_a": "c",
                "claim_id_b": "d",
                "text_a": "C",
                "text_b": "D",
                "human_label": "SUPPORTS",
            },
            {
                "pair_id": "cand_2",
                "claim_id_a": "e",
                "claim_id_b": "f",
                "text_a": "E",
                "text_b": "F",
                "human_label": "",
            },
        ]
    ).to_csv(extra, index=False)

    pairs, meta = load_pairs(
        extra,
        "extra1",
        label_column="human_label",
        ignore_empty_labels=True,
    )
    assert len(pairs) == 1
    assert pairs[0].pair_id == "cand_1"
    assert meta["input_rows"] == 2
    assert meta["ignored_empty_labels"] == 1

    with pytest.raises(SystemExit, match="empty `human_label`"):
        load_pairs(extra, "extra1", label_column="human_label")


def test_duplicate_pair_detection_is_order_independent() -> None:
    first = make_pair("1", "UNRELATED", claim_id_a="a", claim_id_b="b")
    duplicate = make_pair("2", "UNRELATED", claim_id_a="b", claim_id_b="a")
    with pytest.raises(SystemExit, match="same claim pair appears twice"):
        validate_pairs([first, duplicate], audit_pairs=[first])


def test_audit_must_be_a_labeled_subset() -> None:
    full = make_pair("1", "CONTRADICTS")
    audit = make_pair("1", "UNRELATED")
    with pytest.raises(SystemExit, match="does not match"):
        validate_pairs([full], audit_pairs=[audit])


def test_wilson_intervals_bounds() -> None:
    low, high = wilson_ci(0, 4)
    assert low == 0.0
    assert 0.48 < high < 0.50

    low, high = wilson_ci(4, 4)
    assert 0.50 < low < 0.52
    assert high == 1.0

    assert wilson_ci(0, 0) is None


def test_audit_metrics_primary_counts_and_mechanisms() -> None:
    tp1 = make_pair("tp1", "CONTRADICTS")
    tp2 = make_pair("tp2", "CONTRADICTS")
    fp1 = make_pair("fp1", "UNRELATED")
    fp2 = make_pair("fp2", "SUPPORTS")
    fp3 = make_pair("fp3", "UNRELATED")
    audit_pairs = [tp1, tp2, fp1, fp2, fp3]
    full_by_key = {pair.pair_key: pair for pair in audit_pairs}
    results = {
        ("A", "tp1"): make_entry(tp1, "CONTRADICTS", status="CONTRADICTS"),
        ("A", "tp2"): make_entry(tp2, "UNRELATED", status="UNRELATED"),
        ("A", "fp1"): make_entry(fp1, "UNRELATED", status="UNRELATED"),
        ("A", "fp2"): make_entry(fp2, "UNRELATED", status="GATE_DROPPED", llm_called=False),
        ("A", "fp3"): make_entry(fp3, "CONTRADICTS", status="CONTRADICTS"),
    }

    metrics = _audit_metrics(
        SimpleNamespace(key="A"),
        audit_pairs,
        results,
        full_by_key,
    )
    assert metrics["audit_rows_evaluated"] == 5
    assert metrics["audit_complete"] is True
    assert metrics["reviewed_false_positives"] == 3
    assert metrics["false_positives_stopped"] == 2
    assert metrics["false_positives_remaining"] == 1
    assert metrics["true_positives_kept"] == 1
    assert metrics["true_positives_missed"] == 1
    assert metrics["stops_by_mechanism"] == {"gate": 1, "judge": 1}
    assert metrics["misses_by_mechanism"] == {"judge": 1}
    assert metrics["false_positive_suppression_rate"] == pytest.approx(2 / 3)
    assert metrics["true_positive_retention_rate"] == pytest.approx(1 / 2)


def test_missing_audit_rows_are_not_counted_as_stopped() -> None:
    tp = make_pair("tp", "CONTRADICTS")
    fp = make_pair("fp", "UNRELATED")
    metrics = _audit_metrics(
        SimpleNamespace(key="A"),
        [tp, fp],
        {},
        {pair.pair_key: pair for pair in (tp, fp)},
    )
    assert metrics["audit_rows_evaluated"] == 0
    assert metrics["audit_complete"] is False
    assert metrics["false_positives_stopped"] == 0
    assert metrics["true_positives_kept"] == 0
    assert metrics["false_positive_suppression_rate"] is None
    assert metrics["missing_pair_ids"] == ["tp", "fp"]


def test_full_set_metrics_include_precision_recall_and_gate_ci() -> None:
    pairs = [
        make_pair("p1", "CONTRADICTS"),
        make_pair("p2", "CONTRADICTS"),
        make_pair("p3", "UNRELATED"),
        make_pair("p4", "UNRELATED"),
        make_pair("p5", "SUPPORTS"),
    ]
    entries = [
        make_entry(pairs[0], "CONTRADICTS", status="CONTRADICTS"),
        make_entry(pairs[1], "UNRELATED", status="GATE_DROPPED", llm_called=False),
        make_entry(pairs[2], "CONTRADICTS", status="CONTRADICTS"),
        make_entry(pairs[3], "UNRELATED", status="UNRELATED"),
        make_entry(pairs[4], "SUPPORTS", status="SUPPORTS"),
    ]
    variant = SimpleNamespace(
        key="A",
        title="test",
        gate=0.35,
        prompt_kind="current",
        prompt_hash="hash",
        guard=True,
        provider="test",
        model="test-model",
    )
    metrics = _variant_metrics(variant, entries, total_pairs=5, calls_this_run=4)
    assert metrics["confirmed_positives"] == 2
    assert metrics["flagged"] == 2
    assert metrics["true_positives"] == 1
    assert metrics["false_positives"] == 1
    assert metrics["false_negatives"] == 1
    assert metrics["precision"] == pytest.approx(0.5)
    assert metrics["recall"] == pytest.approx(0.5)
    assert metrics["gate_dropped_positives"] == ["p2"]
    assert metrics["gate_dropped_positives_ci95"] is not None
    assert metrics["complete"] is True


def test_noise_comparisons_use_wilson_overlap() -> None:
    def report(
        *,
        fp_rate: float,
        fp_ci: tuple[float, float],
        tp_rate: float,
        tp_ci: tuple[float, float],
        precision: float,
        precision_ci: tuple[float, float],
        recall: float,
        recall_ci: tuple[float, float],
    ) -> dict:
        return {
            "audit": {
                "false_positives_stopped": 1,
                "reviewed_false_positives": 2,
                "false_positive_suppression_rate": fp_rate,
                "false_positive_suppression_ci95": fp_ci,
                "true_positives_kept": 2,
                "confirmed_positives": 4,
                "true_positive_retention_rate": tp_rate,
                "true_positive_retention_ci95": tp_ci,
            },
            "true_positives": 1,
            "flagged": 2,
            "precision": precision,
            "precision_ci95": precision_ci,
            "positives": 4,
            "recall": recall,
            "recall_ci95": recall_ci,
        }

    reports = {
        "A": report(
            fp_rate=0.50,
            fp_ci=(0.30, 0.70),
            tp_rate=0.50,
            tp_ci=(0.20, 0.80),
            precision=0.50,
            precision_ci=(0.20, 0.80),
            recall=0.25,
            recall_ci=(0.05, 0.70),
        ),
        "B": report(
            fp_rate=0.55,
            fp_ci=(0.35, 0.74),
            tp_rate=0.50,
            tp_ci=(0.20, 0.80),
            precision=0.55,
            precision_ci=(0.25, 0.82),
            recall=0.25,
            recall_ci=(0.05, 0.70),
        ),
        "C": report(
            fp_rate=0.90,
            fp_ci=(0.80, 0.96),
            tp_rate=0.90,
            tp_ci=(0.80, 0.96),
            precision=0.90,
            precision_ci=(0.80, 0.96),
            recall=0.90,
            recall_ci=(0.80, 0.96),
        ),
    }
    comparisons = _noise_comparisons(reports)
    labels = {row["label"] for row in comparisons}
    assert "within noise" in labels
    assert "CIs disjoint" in labels


def test_preregistration_header_precedes_results_and_has_no_metrics() -> None:
    pair = make_pair("1", "CONTRADICTS")
    audit = make_pair("1", "CONTRADICTS")
    variant = Variant(
        key="A",
        title="Test",
        gate=0.95,
        prompt_kind="old",
        prompt="prompt",
        guard=False,
        provider="test",
        model="test-model",
    )
    args = SimpleNamespace(limit=None, delay=0.0, note="", report_only=False)
    report = build_preregistration_report(
        variants=[variant],
        pairs_full=[pair],
        cache_meta={},
        args=args,
        dataset_meta=[
            {
                "path": "test.csv",
                "rows": 1,
                "labels": {"CONTRADICTS": 1},
                "source_tag": "base",
            }
        ],
        old_prompt="old prompt",
        audit_pairs=[audit],
        audit_meta={
            "path": "audit.csv",
            "rows": 1,
            "labels": {"CONTRADICTS": 1},
            "old_judge_flagged": 1,
            "verified_false_positives": 0,
            "confirmed_positives": 1,
        },
    )
    markdown = render_markdown(report)
    definitions = markdown.index("## Pre-registered metric definitions")
    layout = markdown.index("## Pre-registered table layout")
    results = markdown.index("## Results")
    assert definitions < results
    assert layout < results
    assert "No results yet" in markdown
    assert "within noise" in markdown
    assert "| Variant | Audit rows evaluated" not in markdown


def test_interpretation_has_exactly_three_sentences() -> None:
    audit = {
        "false_positives_stopped": 10,
        "reviewed_false_positives": 20,
        "false_positive_suppression_rate": 0.5,
        "false_positive_suppression_ci95": (0.3, 0.7),
        "true_positives_kept": 2,
        "confirmed_positives": 4,
        "true_positive_retention_rate": 0.5,
        "true_positive_retention_ci95": (0.2, 0.8),
    }
    variants = {
        "A": {
            "variant": "A",
            "audit": audit,
            "flagged": 2,
            "true_positives": 1,
            "positives": 4,
            "precision": 0.5,
            "precision_ci95": (0.2, 0.8),
            "recall": 0.25,
            "recall_ci95": (0.05, 0.7),
            "macro_f1": 0.4,
            "gate": 0.95,
            "gate_dropped_positives": [],
            "complete": True,
            "evaluated": 10,
            "total_pairs": 10,
        },
        "C": {
            "variant": "C",
            "audit": audit,
            "flagged": 1,
            "true_positives": 1,
            "positives": 4,
            "precision": 1.0,
            "precision_ci95": (0.2, 1.0),
            "recall": 0.25,
            "recall_ci95": (0.05, 0.7),
            "macro_f1": 0.5,
            "gate": 0.35,
            "gate_dropped_positives": ["2"],
            "complete": True,
            "evaluated": 10,
            "total_pairs": 10,
        },
    }
    report = {
        "meta": {
            "audit": {"rows_total": 20},
            "evaluated_rows": 10,
            "confirmed_positives": {"full": 4},
        },
        "variants": variants,
        "noise_comparisons": [
            {"label": "within noise"},
            {"label": "CIs disjoint"},
        ],
    }
    text = _interpretation(report)
    assert text.count(". ") == 2
    assert text.endswith(".")
    assert "within noise" in text
