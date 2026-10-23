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
python eval/run_eval.py --predictor llm --dataset axion_pairs.csv

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

## The reference set: `axion_pairs.csv`

The dataset to report on is **`eval/Data/axion_pairs.csv`** — 286 cross-paper
pairs with reviewed labels. Rebuild it with:

```bash
python eval/Data/build_reference_set.py
```

Provenance (the only genuinely reviewed labels in the repo):

- **`contradicts_review_labeled.csv` (224 pairs).** The production agent
  auto-detected these as CONTRADICTS; a reviewer then audited each one against
  the 3-question rubric in `label_contradicts.py` (same topic? agree? genuinely
  conflict?). The audit found only **4 true CONTRADICTS**, 11 SUPPORTS and
  209 UNRELATED — i.e. the detector's precision on this sample is **~1.8%**.
  These reviewed labels are treated as ground truth.
- **`labeled_pairs_cleaned.csv` (62 pairs after de-duplication).** Cross-paper,
  all UNRELATED, unverified provenance — included as extra negatives and tagged
  `source=labeled_pairs_cleaned` so they can be filtered out.

Composition: **4 CONTRADICTS / 11 SUPPORTS / 271 UNRELATED** (0 same-paper).
Recorded baselines (`eval/results/*_axion_pairs.json`):

| predictor | accuracy | macro F1 | CONTRADICTS P / R / F1 |
| :--- | ---: | ---: | :--- |
| majority (all UNRELATED) | 0.9476 | 0.3244 | 0.00 / 0.00 / 0.00 |
| random (seed 0) | 0.3706 | 0.2191 | — |
| llm (groq `openai/gpt-oss-20b`) | 0.8427 | 0.4822 | 0.154 / 0.500 / 0.235 |

The LLM run made 0 parse failures and predicted 13 CONTRADICTS for 4 real ones —
i.e. it reproduces the low precision the human audit found (~1.8% on the
original 224 auto-detections; 15.4% here, since the eval model differs from the
one that originally wrote the graph edges). Accuracy looks healthy only because
271/286 pairs are negatives.

## Judge ablation (pre-registered)

The four-variant judge ablation is pre-registered in
`eval/results/judge_ablation.md`. Its primary metric is the 224-row human audit
(220 verified false positives, 4 confirmed contradictions), not the full-set
accuracy:

- **A** — gate 0.95, old prompt, guard off, Groq `openai/gpt-oss-20b`.
- **B** — gate 0.35, old prompt, guard off, Groq `openai/gpt-oss-20b`.
- **C** — gate 0.35, current prompt, guard on, Groq `openai/gpt-oss-20b`.
- **D** — same as C, but Gemini `gemini-3.8-flash` as an alternative judge.

Results are in `eval/results/judge_ablation.md` (definitions and table layout
above the results) and `eval/results/judge_ablation.json`. The launch summary
is `eval/results/ablation_summary.md`; chart-ready aggregates are in
`eval/results/ablation_chart_data.json`. The resumable cache is
`eval/results/ablation_cache.jsonl`, keyed by
`(variant, pair_id, signature)`.

Headline audit results: A stopped 208/220 verified false positives and kept 3/4
confirmed contradictions; B stopped 219/220 and kept 0/4; C stopped 220/220 and
kept 1/4; D stopped 220/220 and kept 0/4. These are preliminary: only four
positives, and 18/24 pairwise comparisons are within noise. No verified false
positive survives all four variants; pair 171 is the only one still flagged by
B. The 0.35 gate drops pair 124 (distance 0.501931), one of the four confirmed
contradictions, before B/C/D judge it.

A–C use the current `openai/gpt-oss-20b`. The original 1.8% production figure
came from `llama-3.1-8b-instant` at gate 0.95 with the old prompt, so the model
swap itself is unmeasured. D changes provider and model; it is an alternative
judge, not an assumed upgrade.

Reproduce offline (no provider calls):

```bash
python eval/judge_ablation.py --report-only
python eval/build_ablation_summary.py
```

Check quota and the remaining cache plan without calling a provider:

```bash
python eval/judge_ablation.py --dry-run
```

A live run is resumable and deliberately single-attempt (no retry/fallback):

```bash
python eval/judge_ablation.py
```

Provider quota/error stops the run and leaves completed rows cached. The
summary builder reads only the report, the two reviewed CSVs, and the cache; it
never writes labels. Do not use
`eval/human_review/unverified/contradiction_candidates_review_researched.csv`
as a source; it is unverified and is not part of the ablation.

### Why the old splits are unusable

`train.csv` / `val.csv` / `test.csv` label almost every SUPPORTS/CONTRADICTS
pair as **same-paper**, which `check_pair()` refuses to compare. After the
harness's same-paper exclusion they are 100% UNRELATED:

| split | CONTRADICTS | SUPPORTS | UNRELATED | cross-paper rows |
| :--- | ---: | ---: | ---: | ---: |
| train | 3 | 83 | 124 | 48 (all UNRELATED) |
| val | 1 | 17 | 27 | 10 (all UNRELATED) |
| test | 1 | 18 | 26 | 10 (all UNRELATED) |

On `test.csv` the majority baseline scores accuracy 1.0 / macro F1 0.33 — pure
artifact. `eval/Data/Labeled_pairs.csv` (the split source) is 0 bytes.
`--include-same-paper` shows the other view, but those pairs are never scored in
production.

### Reading the numbers

- Report `f1_macro` (not accuracy): with 271/286 negatives, accuracy is driven
  entirely by the majority class.
- **CONTRADICTS has only 4 examples**, so its per-class F1 is noisy — treat the
  audited precision (~1.8%) as the headline quality signal, not a single F1.
- The `warnings` array and `predictor_diagnostics` (below) are part of the
  result — print them alongside any metric.

### Parse-failure instrumentation

`check_pair()` used to collapse SAME_CLAIM, SAME_PAPER, UNRELATED and JSON parse
failures into a single `None`. It now accepts an optional `diagnostics` dict and
records `diagnostics["status"]`; the LLM predictor tallies these and the JSON
result carries a `predictor_diagnostics` block, e.g.:

```json
"predictor_diagnostics": {"parse_failures": 2, "statuses": {"UNRELATED": 250, "SUPPORTS": 20, "CONTRADICTS": 12, "PARSE_FAILURE": 2}}
```

A parse failure is a *model failure*, not a negative — the harness emits a
warning whenever any occur.

## Stale results

`eval/results/baseline_llm.json` (generated 2026-08-02, self-labelled
"OLD CONTAMINATED"; accuracy 0.489 / macro F1 0.219) was produced by the old
script that conflated same-paper pairs, UNRELATED verdicts and parse failures,
so its denominator is wrong. It is kept only for history — the current LLM
baseline is `eval/results/llm_axion_pairs.json`.

`eval/results/majority_test.json` / `random_test.json` are old, same-paper-
collapsed baselines for the old `test.csv`. The current reference baselines are
`eval/results/{majority,random,llm}_axion_pairs.json`.

## Metric targets

Now measurable on `axion_pairs.csv` (not yet met — the audited precision is
~1.8%, so there is real headroom):

| Metric | Target | Notes |
| :--- | :--- | :--- |
| `f1_macro` | ≥ 0.55 | Over all three classes, cross-paper pairs |
| CONTRADICTS precision | ≥ 0.60 | Audited production precision is ~0.018 |
| CONTRADICTS recall | ≥ 0.60 | Recall matters more than precision here |
| `latency_ms.p95` | ≤ 4000 | Per pair, single LLM call |

The audited precision above is the original production-agent sample. The
current-model re-measurement, with its gate/guard variants and Wilson intervals,
is in `eval/results/ablation_summary.md`; it is pilot evidence because the audit
contains only four confirmed positives.

## Layout

```
eval/
  run_eval.py            # single entry point (CLI + run())
  baseline_llm_eval.py   # deprecated shim -> run_eval.py --predictor llm
  judge_ablation.py      # pre-registered four-variant judge ablation
  build_ablation_summary.py # offline summary + chart-data builder
  metrics.py             # pure metric computation
  dataset.py             # loading, validation, same-paper exclusion, composition
  predictors.py          # majority / random / llm predictors
  results/               # generated JSON results
    judge_ablation.md/json       # full ablation report
    ablation_summary.md          # launch summary
    ablation_chart_data.json     # chart-ready aggregates
    ablation_cache.jsonl         # resumable judge cache
  Data/
    axion_pairs.csv          # reference set (286 reviewed cross-paper pairs)
    contradicts_review_labeled.csv # 224-row human audit
    build_reference_set.py   # rebuilds axion_pairs.csv from reviewed labels
    ...                      # raw exports / prep scripts
  models/                # empty (planned, unused)
```
