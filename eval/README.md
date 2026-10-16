# Axion Evaluation Harness (`eval/`)

Evaluates the claim-relationship classifier (`agents/contradiction.check_pair`)
on labelled claim pairs. All logic is shared with the CLI — there is a single
entry point:

```bash
python eval/run_eval.py --predictor <majority|random|llm> --dataset <file>
```

## Quick start

```bash
# Offline smoke test — no Neo4j / ChromaDB / LLM required (used by CI)
python eval/run_eval.py --predictor majority

# Reproducible randomness
python eval/run_eval.py --predictor random --seed 7

# Real LLM baseline (needs GROQ_API_KEY / GEMINI_API_KEY and network)
python eval/run_eval.py --predictor llm --dataset test.csv

# Legacy entry point still works (delegates to run_eval.py)
python eval/baseline_llm_eval.py
```

Results are written to `eval/results/<predictor>_<dataset>.json` with the full
metric set, per-pair predictions, dataset composition, and any warnings.

## What the output contains

| Field | Meaning |
| :--- | :--- |
| `metrics.accuracy` | Overall accuracy |
| `metrics.f1_macro` | **Unweighted** mean F1 over `CONTRADICTS`, `SUPPORTS`, `UNRELATED` — the headline number |
| `metrics.f1_weighted` | Support-weighted F1 (dominated by the majority class) |
| `metrics.per_class` | Precision / recall / F1 / support per class |
| `metrics.confusion_matrix` | True × predicted counts |
| `metrics.latency_ms` | avg / p50 / p95 / max per pair |
| `dataset.*` | Input vs evaluated row counts, exclusions, class mix |
| `warnings` | Conditions that make the headline number misleading |

`f1_macro` is averaged over all three classes even when one never appears, so a
single-class run is penalised rather than scoring a misleading 1.0.

## ⚠️ Known dataset problems (read before trusting any number)

1. **The labelled splits cannot measure production behaviour.**
   In `train.csv`, `val.csv` and `test.csv`, **every** `SUPPORTS` and
   `CONTRADICTS` pair is a *same-paper* pair (same `arxiv_id`), but
   `check_pair()` deliberately refuses to compare two claims from the same
   paper. After the harness excludes same-paper pairs (the production-aligned
   default), the test split is **100% UNRELATED**:

   | split | CONTRADICTS | SUPPORTS | UNRELATED | cross-paper rows |
   | :--- | ---: | ---: | ---: | ---: |
   | train | 3 | 83 | 124 | 48 (all UNRELATED) |
   | val | 1 | 17 | 27 | 10 (all UNRELATED) |
   | test | 1 | 18 | 26 | 10 (all UNRELATED) |

   Consequence: the majority baseline scores **accuracy 1.0 / macro F1 0.33**
   on the default run. Any accuracy close to 1.0 here is an artifact.

   Use `--include-same-paper` to see the other view (majority baseline:
   accuracy 0.578 / macro F1 0.244) — but note that view includes pairs the
   production agent never scores.

2. **Class imbalance.** Test set is 26 UNRELATED / 18 SUPPORTS / 1 CONTRADICTS.
   Macro F1 for CONTRADICTS rests on a single example; treat it as anecdotal.

3. **`eval/Data/Labeled_pairs.csv` is 0 bytes** (this is the same file as
   lowercase `labeled_pairs.csv` on case-insensitive filesystems). The source
   dataset that produced the train/val/test splits is therefore missing;
   `eval/Data/split_dataset.py` cannot regenerate the splits. The splits
   themselves are still present.

4. **`eval/Data/labeled_pairs_cleaned.csv` is 100% UNRELATED** (68 rows) — it
   contains no positive examples and must not be used as an eval set.

5. **`check_pair()` collapses UNRELATED, same-paper and JSON-parse failures
   into a single `None`.** The harness works around same-paper pairs up front,
   so a `None` is read as UNRELATED, but a silent parse failure is still
   indistinguishable from a genuine negative. Instrumenting `check_pair` to
   expose this is tracked in `progress.md` (Track D).

### Implications

- A meaningful eval **must** use cross-paper pairs with real CONTRADICTS /
  SUPPORTS labels. The current labelled data does not contain enough of them.
- Until the dataset is rebuilt, report `f1_macro` (not accuracy), always print
  the class mix and `warnings`, and never cite a single run as proof of quality.

## Stale results

`eval/results/baseline_llm.json` (generated 2026-08-02, self-labelled
"OLD CONTAMINATED"; accuracy 0.489 / macro F1 0.219) was produced by the old
script that conflated same-paper pairs, UNRELATED verdicts and parse failures,
so its denominator is wrong. It is kept only for history — regenerate with
`python eval/run_eval.py --predictor llm` after the dataset is fixed.

`eval/results/majority_test.json` is a deterministic offline reference baseline
for regression comparisons.

## Proposed metric targets (not yet met — no valid data to verify against)

| Metric | Target | Notes |
| :--- | :--- | :--- |
| `f1_macro` | ≥ 0.55 | Over all three classes, cross-paper pairs |
| CONTRADICTS recall | ≥ 0.60 | Recall matters more than precision here |
| `latency_ms.p95` | ≤ 4000 | Per pair, single LLM call |

## Layout

```
eval/
  run_eval.py            # single entry point (CLI + run())
  baseline_llm_eval.py   # deprecated shim -> run_eval.py --predictor llm
  metrics.py             # pure metric computation
  dataset.py             # loading, validation, same-paper exclusion, composition
  predictors.py          # majority / random / llm predictors
  results/               # generated JSON results
  Data/                  # labelled pair CSVs and data-prep scripts (ad-hoc)
  models/                # empty (planned, unused)
```
