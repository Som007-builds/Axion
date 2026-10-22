# Judge ablation — 2026-10-22 — pre-registered

**Status:** `preregistered`; this file intentionally contains no results. The definitions and table layouts below were written before this file contained any results.

**Full reviewed set:** `eval\Data\axion_pairs.csv` (286 labeled rows: CONTRADICTS 4, SUPPORTS 11, UNRELATED 271).
**Full-set caveat:** 62 rows come from `labeled_pairs_cleaned` (unverified negative provenance) and affect only the secondary full-set metrics; the primary audit uses the 224 reviewed rows.
**Audit set (primary metric):** `eval\Data\contradicts_review_labeled.csv` (224 rows: CONTRADICTS 4, SUPPORTS 11, UNRELATED 209); 224 old production-agent CONTRADICTS auto-detections, 220 verified false positives, 4 confirmed contradictions.
**Audit provenance:** All rows are production-agent CONTRADICTS auto-detections audited against the rubric in eval/Data/label_contradicts.py; see eval/README.md. The audit's old judge is the production agent that wrote the original CONTRADICTS edges, not variant A's pre-change setup.
**Confirmed human CONTRADICTS labels:** 4 confirmed human CONTRADICTS labels in the full set; 4 in the audit subset; labels were read from the CSVs and never generated or filled in.
**Variant models and gates:** A: gate 0.95, old prompt, guard off, `groq/openai/gpt-oss-20b`; B: gate 0.35, old prompt, guard off, `groq/openai/gpt-oss-20b`; C: gate 0.35, current prompt, guard on, `groq/openai/gpt-oss-20b`; D: gate 0.35, current prompt, guard on, `gemini/gemini-3.8-flash`.
**Prompt hashes:** old `4c7e1d55997e34320e3195bbf43002d6a74480f9691543b4d1a1fecfae6302b0`; current `2a8e00957a0015016b699ba52b916ffa986a581ab899fac56ad8fdf290b53f9e`.
**Embedding:** `all-MiniLM-L6-v2`; distance = 1 - cosine similarity, computed locally with sentence-transformers.
**Cache:** `eval\results\ablation_cache.jsonl` (999 lines, 0 malformed); resumable and keyed by variant signature and `(variant, pair_id)`; a run may reuse cached rows and make fewer provider calls.
**Optional extra:** `eval\human_review\contradiction_candidates_review.csv` was not present; no extra rows were added.
**Rows:** 286 in the full reviewed set; 4 confirmed contradictions.

## Pre-registered metric definitions

- **Primary audit metric.** The audit file is fixed before the run. A **verified false positive** is an audit row whose human label is not `CONTRADICTS`; it is **stopped** when the variant's final prediction is not `CONTRADICTS`. Gate drops, guard demotions, parse failures, `SUPPORTS`, and `UNRELATED` all count as stopped. A **confirmed true positive** is an audit row labeled `CONTRADICTS`; it is **kept** when the final prediction is `CONTRADICTS`. Missing rows are reported as missing, never as stopped or kept.
- **Primary rates.** False-positive suppression is `stopped / reviewed false positives`; true-positive retention is `kept / confirmed positives evaluated`. Both use Wilson 95% confidence intervals. `n/a` means the denominator is zero.
- **Secondary full-set metrics.** On the full reviewed set, `CONTRADICTS` precision is `TP / (TP + FP)`, recall is `TP / (TP + FN)`, and macro F1 is the unweighted mean of the three class F1 scores. Precision and recall use Wilson 95% intervals; macro F1 is a point estimate, not a proportion.
- **Gate-dropped positives.** A confirmed `CONTRADICTS` pair whose local MiniLM distance is greater than the variant gate, so it never reaches the judge. The count is reported with `dropped / evaluated positives` and a Wilson 95% interval.
- **Noise rule.** For every pairwise variant comparison, the difference is marked `within noise` when the two Wilson 95% intervals overlap; otherwise it is marked `CIs disjoint`. Overlap is a descriptive screen, not a hypothesis test.
- **Calls and tokens.** `LLM calls` counts judged rows represented in the results. Tokens are the provider-reported prompt, completion, and total usage where available; `n/a` means the provider did not return usage. Cache reuse makes zero new calls.
- **No generated labels.** Empty `human_label` rows in an extra file are ignored; empty labels in the base or audit files are errors. The harness never writes or repairs a label.

## Pre-registered table layout

- **Primary audit table:** `Variant | Audit rows evaluated | Verified FPs stopped / reviewed | FP suppression (95% CI) | Verified TPs kept / confirmed | TP retention (95% CI) | FPs remaining | TPs missed`.
- **Secondary full-set table:** `Variant | Gate | Prompt / guard | Model | Evaluated | CONTRADICTS flagged | TP | FP | FN | Precision (95% CI) | Recall (95% CI) | Macro F1 | Gate-dropped positives (rate, 95% CI) | LLM calls | Tokens`.
- **Stop-mechanism table:** `Variant | FPs stopped by gate | by guard | by judge | other | TPs kept | TPs lost to gate | lost to guard | lost to judge | lost to other`.
- **Pairwise noise table:** `Metric | Comparison | A (95% CI) | B (95% CI) | Difference | CI overlap | Label`.
- **Known-positives table:** `Pair | Distance |` one column per requested variant, with `CONTRADICTS`, `SUPPORTS`, `UNRELATED`, `UNRELATED (gate)`, `UNRELATED (guard)`, or `UNRELATED (parse)`.

## Results

No results yet. Run `--dry-run` to check quota, then run the same command without `--dry-run` to fill this section; definitions above must remain unchanged.
