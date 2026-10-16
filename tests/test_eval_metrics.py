# tests/test_eval_metrics.py
"""
Hermetic tests for the eval harness (no Neo4j / ChromaDB / LLM).

Covers:
  * metric computation + per-class reporting over the full class list
  * confusion-matrix shape
  * deterministic same-paper exclusion
  * end-to-end run() with the offline majority predictor, including the
    single-class warnings that make the dataset limitation explicit
"""
import json

import pandas as pd
import pytest

from eval.dataset import composition, prepare_pairs
from eval.metrics import compute_metrics
from eval.run_eval import run


# ─── metrics ──────────────────────────────────────────────────────────────────

class TestComputeMetrics:

    def test_perfect_predictions(self):
        y = ["CONTRADICTS", "SUPPORTS", "UNRELATED"]
        m = compute_metrics(y, y)
        assert m["n"] == 3
        assert m["accuracy"] == 1.0
        assert m["f1_macro"] == 1.0
        assert all(m["per_class"][c]["f1"] == 1.0 for c in y)

    def test_absent_class_is_reported_with_zero_support(self):
        m = compute_metrics(["UNRELATED", "UNRELATED"], ["UNRELATED", "UNRELATED"])
        assert m["per_class"]["CONTRADICTS"]["support"] == 0
        assert m["per_class"]["SUPPORTS"]["support"] == 0
        # macro is averaged over all three classes, so a single-class run is penalised
        assert round(m["f1_macro"], 4) == round(1.0 / 3.0, 4)

    def test_confusion_matrix_shape_and_counts(self):
        m = compute_metrics(["SUPPORTS", "UNRELATED"], ["UNRELATED", "UNRELATED"])
        cm = m["confusion_matrix"]
        assert cm["SUPPORTS"]["UNRELATED"] == 1
        assert cm["UNRELATED"]["UNRELATED"] == 1
        assert cm["CONTRADICTS"]["CONTRADICTS"] == 0

    def test_empty_input_is_safe(self):
        m = compute_metrics([], [])
        assert m["n"] == 0
        assert m["accuracy"] == 0.0
        assert m["latency_ms"]["avg"] == 0.0

    def test_latency_stats(self):
        m = compute_metrics(["UNRELATED"], ["UNRELATED"], latencies=[10.0, 20.0, 30.0])
        assert m["latency_ms"]["p50"] == 20.0
        assert m["latency_ms"]["max"] == 30.0
        assert m["latency_ms"]["avg"] == 20.0


# ─── dataset preparation ──────────────────────────────────────────────────────

def _frame(rows):
    return pd.DataFrame(rows)


class TestPreparePairs:

    def test_same_paper_rows_are_excluded_deterministically(self):
        df = _frame([
            {"claim_a_arxiv_id": "1", "claim_b_arxiv_id": "1", "claim_a_id": "a", "claim_b_id": "b", "label": "SUPPORTS"},
            {"claim_a_arxiv_id": "1", "claim_b_arxiv_id": "2", "claim_a_id": "a", "claim_b_id": "c", "label": "UNRELATED"},
        ])
        prepared, report = prepare_pairs(df)
        assert len(prepared) == 1
        assert prepared.iloc[0]["label"] == "UNRELATED"
        assert report["excluded_same_paper"] == 1

    def test_include_same_paper_keeps_them(self):
        df = _frame([
            {"claim_a_arxiv_id": "1", "claim_b_arxiv_id": "1", "claim_a_id": "a", "claim_b_id": "b", "label": "SUPPORTS"},
        ])
        prepared, report = prepare_pairs(df, exclude_same_paper=False)
        assert len(prepared) == 1
        assert report["excluded_same_paper"] == 0

    def test_composition_reports_all_classes(self):
        df = _frame([{"label": "UNRELATED"}, {"label": "UNRELATED"}, {"label": "SUPPORTS"}])
        comp = composition(df)
        assert comp["total"] == 3
        assert comp["counts"] == {"CONTRADICTS": 0, "SUPPORTS": 1, "UNRELATED": 2}


# ─── end-to-end run() ─────────────────────────────────────────────────────────

class TestRunEval:

    def _write_csv(self, tmp_path):
        path = tmp_path / "tiny.csv"
        _frame([
            {"claim_a_id": "1", "claim_b_id": "2", "claim_a_text": "A", "claim_b_text": "B",
             "claim_a_arxiv_id": "1111", "claim_b_arxiv_id": "1111", "label": "SUPPORTS"},
            {"claim_a_id": "3", "claim_b_id": "4", "claim_a_text": "C", "claim_b_text": "D",
             "claim_a_arxiv_id": "2222", "claim_b_arxiv_id": "3333", "label": "UNRELATED"},
        ]).to_csv(path, index=False)
        return path

    def test_run_writes_json_and_flags_single_class(self, tmp_path):
        csv = self._write_csv(tmp_path)
        out = tmp_path / "out.json"
        results = run(dataset=str(csv), predictor="majority", output=str(out), verbose=False)

        assert out.is_file()
        on_disk = json.loads(out.read_text(encoding="utf-8"))
        assert on_disk["predictor"] == "majority"
        assert on_disk["dataset"]["input_rows"] == 2
        assert on_disk["dataset"]["evaluated_rows"] == 1
        assert on_disk["dataset"]["excluded_same_paper"] == 1

        # only the cross-paper UNRELATED pair is evaluated -> single class
        assert results["metrics"]["n"] == 1
        assert any("single-class" in w for w in results["warnings"])
        assert any("SUPPORTS has 0" in w for w in results["warnings"])

    def test_unknown_predictor_raises(self, tmp_path):
        csv = self._write_csv(tmp_path)
        with pytest.raises(ValueError):
            run(dataset=str(csv), predictor="does-not-exist", verbose=False)

    def test_dataset_relative_to_eval_data(self):
        # 'test.csv' resolves inside eval/Data regardless of CWD
        results = run(dataset="test.csv", predictor="majority", verbose=False)
        assert results["dataset"]["path"] == "eval/Data/test.csv"
