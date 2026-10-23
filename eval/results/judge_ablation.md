# Judge ablation — 2026-10-23

**Run status:** `complete`
**Pre-registration:** the definitions and table layouts below were written before results; the results in `## Results` use them unchanged.
**Rendering:** generated from cache; no provider calls were made in this step.

**Full reviewed set:** `eval\Data\axion_pairs.csv` (286 labeled rows: CONTRADICTS 4, SUPPORTS 11, UNRELATED 271).
**Full-set caveat:** 62 rows come from `labeled_pairs_cleaned` (unverified negative provenance) and affect only the secondary full-set metrics; the primary audit uses the 224 reviewed rows.
**Audit set (primary metric):** `eval\Data\contradicts_review_labeled.csv` (224 rows: CONTRADICTS 4, SUPPORTS 11, UNRELATED 209); 224 old production-agent CONTRADICTS auto-detections, 220 verified false positives, 4 confirmed contradictions.
**Audit provenance:** All rows are production-agent CONTRADICTS auto-detections audited against the rubric in eval/Data/label_contradicts.py; see eval/README.md. The audit's old judge is the production agent that wrote the original CONTRADICTS edges, not variant A's pre-change setup.
**Confirmed human CONTRADICTS labels:** 4 confirmed human CONTRADICTS labels in the full set; 4 in the audit subset; labels were read from the CSVs and never generated or filled in.
**Variant models and gates:** A: gate 0.95, old prompt, guard off, `groq/openai/gpt-oss-20b`; B: gate 0.35, old prompt, guard off, `groq/openai/gpt-oss-20b`; C: gate 0.35, current prompt, guard on, `groq/openai/gpt-oss-20b`; D: gate 0.35, current prompt, guard on, `gemini/gemini-3.8-flash`.
**Model interpretation:** A–C use the current `openai/gpt-oss-20b`; the original 1.8% production figure came from the older `llama-3.1-8b-instant` run at gate 0.95 with the old prompt. A re-measures the old prompt and gate on the current model; the model swap itself is unmeasured. D is an alternative judge from a different provider, not assumed stronger.
**Prompt hashes:** old `4c7e1d55997e34320e3195bbf43002d6a74480f9691543b4d1a1fecfae6302b0`; current `2a8e00957a0015016b699ba52b916ffa986a581ab899fac56ad8fdf290b53f9e`.
**Embedding:** `all-MiniLM-L6-v2`; distance = 1 - cosine similarity, computed locally with sentence-transformers.
**Cache:** `eval\results\ablation_cache.jsonl` (1144 lines, 0 malformed); resumable and keyed by `(variant, pair_id, signature)`; a stale signature cannot be returned by a lookup, and a run may reuse cached rows and make fewer provider calls.
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

### Primary: verified false-positive suppression (audit set)

| Variant | Audit rows evaluated | Verified FPs stopped / reviewed | FP suppression (95% CI) | Verified TPs kept / confirmed | TP retention (95% CI) | FPs remaining | TPs missed |
|---|---:|---:|---|---:|---|---:|---:|
| A | 224/224 | 208/220 | 0.945 [0.907, 0.969] | 3/4 | 0.750 [0.301, 0.954] | 12 | 1 |
| B | 224/224 | 219/220 | 0.995 [0.975, 0.999] | 0/4 | 0.000 [0.000, 0.490] | 1 | 4 |
| C | 224/224 | 220/220 | 1.000 [0.983, 1.000] | 1/4 | 0.250 [0.046, 0.699] | 0 | 3 |
| D | 224/224 | 220/220 | 1.000 [0.983, 1.000] | 0/4 | 0.000 [0.000, 0.490] | 0 | 4 |

Denominators are the evaluated audit rows; the audit contains 220 verified false positives and 4 confirmed contradictions. A partial variant does not count unevaluated audit rows as stopped or kept.

### Secondary: full reviewed set

| Variant | Gate | Prompt / guard | Model | Evaluated | CONTRADICTS flagged | TP | FP | FN | Precision (95% CI) | Recall (95% CI) | Macro F1 | Gate-dropped positives (rate, 95% CI) | LLM calls | Tokens |
|---|---:|---|---|---:|---:|---:|---:|---:|---|---|---:|---|---:|---:|
| A | 0.95 | old / off | groq/openai/gpt-oss-20b | 286/286 | 15 | 3 | 12 | 1 | 0.200 [0.070, 0.452] | 0.750 [0.301, 0.954] | 0.532 | 0/4 (0.000 [0.000, 0.490]) | 286 | 122950 |
| B | 0.35 | old / off | groq/openai/gpt-oss-20b | 286/286 | 1 | 0 | 1 | 4 | 0.000 [0.000, 0.793] | 0.000 [0.000, 0.490] | 0.354 | 1/4 (0.250 [0.046, 0.699]) | 34 | 15261 |
| C | 0.35 | current / on | groq/openai/gpt-oss-20b | 286/286 | 1 | 1 | 0 | 3 | 1.000 [0.207, 1.000] | 0.250 [0.046, 0.699] | 0.514 | 1/4 (0.250 [0.046, 0.699]) | 34 | 26402 |
| D | 0.35 | current / on | gemini/gemini-3.8-flash | 286/286 | 0 | 0 | 0 | 4 | n/a | 0.000 [0.000, 0.490] | 0.380 | 1/4 (0.250 [0.046, 0.699]) | 34 | 22058 |

The full-set denominators are evaluated rows, so a partial variant is not compared as if it had seen the whole set. `LLM calls` counts rows represented in the results; `calls_this_run` in the JSON is zero for a cache-only render.

### Stop mechanisms on audit false positives

| Variant | FPs stopped by gate | by guard | by judge | other | TPs kept | TPs lost to gate | lost to guard | lost to judge | lost to other |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 0 | 0 | 208 | 0 | 3 | 0 | 0 | 1 | 0 |
| B | 190 | 0 | 29 | 0 | 0 | 1 | 0 | 3 | 0 |
| C | 190 | 0 | 30 | 0 | 1 | 1 | 0 | 2 | 0 |
| D | 190 | 0 | 30 | 0 | 0 | 1 | 0 | 3 | 0 |

### Known human CONTRADICTS pairs

| Pair | Distance | A | B | C | D |
|---|---:|---|---|---|---|
| 0 | 0.180160 | CONTRADICTS | UNRELATED | UNRELATED | UNRELATED |
| 96 | 0.247491 | CONTRADICTS | UNRELATED | UNRELATED | UNRELATED |
| 124 | 0.501931 | CONTRADICTS | UNRELATED (gate) | UNRELATED (gate) | UNRELATED (gate) |
| 215 | 0.274785 | UNRELATED | SUPPORTS | CONTRADICTS | UNRELATED |

### Gate check: all confirmed contradictions

| Pair | Distance | Gate 0.35 | Dropped before judge? |
|---|---:|---:|---|
| 0 | 0.180160 | 0.35 | no |
| 96 | 0.247491 | 0.35 | no |
| 124 | 0.501931 | 0.35 | yes |
| 215 | 0.274785 | 0.35 | no |

Pair `124` is above the 0.35 gate, so B, C, and D never send it to the judge; A keeps it.

### Judge self-consistency (A vs B)

A and B use the same model and old prompt; only the gate differs. On the 34 pairs that pass the 0.35 gate, 34 have a cached final verdict for both variants.

| Gate-pass pairs | Compared | Identical | Different | Identical rate (95% CI) |
|---:|---:|---:|---:|---|
| 34 | 34 | 22 | 12 | 0.647 [0.479, 0.785] |

| Pair | Distance | Human label | A final | B final |
|---|---:|---|---|---|
| 0 | 0.180160 | CONTRADICTS | CONTRADICTS | UNRELATED |
| 9 | 0.265397 | UNRELATED | CONTRADICTS | UNRELATED |
| 11 | 0.313643 | UNRELATED | SUPPORTS | UNRELATED |
| 48 | 0.343385 | UNRELATED | SUPPORTS | UNRELATED |
| 58 | 0.327358 | UNRELATED | UNRELATED | SUPPORTS |
| 96 | 0.247491 | CONTRADICTS | CONTRADICTS | UNRELATED |
| 100 | 0.304710 | UNRELATED | UNRELATED | SUPPORTS |
| 109 | 0.216685 | UNRELATED | SUPPORTS | UNRELATED |
| 141 | 0.209399 | UNRELATED | CONTRADICTS | SUPPORTS |
| 171 | 0.340444 | UNRELATED | UNRELATED | CONTRADICTS |
| 207 | 0.277834 | SUPPORTS | SUPPORTS | UNRELATED |
| 215 | 0.274785 | CONTRADICTS | UNRELATED | SUPPORTS |

This is a consistency check, not an accuracy metric; the gate excludes 252 pairs from B, so the comparison is conditional on passing 0.35.

### C without guard (offline counterfactual)

| Configuration | Flagged | TP | FP | FN | Audit FPs stopped | Audit TPs kept | Guard demotions |
|---|---:|---:|---:|---:|---:|---:|---:|
| C final | 1 | 1 | 0 | 3 | 220/220 | 1/4 | 0 |
| C without guard | 1 | 1 | 0 | 3 | 220/220 | 1/4 | 0 |

The cache stores the raw pre-demotion verdict for C. A guard-demoted raw `CONTRADICTS` would become `CONTRADICTS` here; no provider call is made. C had 0 guard demotions (0 of them raw `CONTRADICTS`), so the guard contributes nothing on this dataset. Because B and C share the 0.35 gate and model, the B-vs-C difference is attributable to the prompt, not the guard.

### Verified false positives still flagged

Each list shows up to 10 audit false positives whose final prediction is still `CONTRADICTS`. Claim texts are copied from `eval/Data/axion_pairs.csv`; only Markdown pipe escaping is applied.

**A — 12 of 220 verified false positives still flagged (showing 10):**

- `5` (distance 0.461685): Claim A: Our method improves the accuracy from 74.4% to 82.1% on GSM8K. Claim B: PaLM 540B with standard prompting achieves a solve rate of 55% on the GSM8K benchmark of math word problems.
- `9` (distance 0.265397): Claim A: Least-to-most prompting outperforms chain-of-thought prompting on tasks requiring compositional generalization. Claim B: Experiments on three large language models show that chain-of-thought prompting improves performance on a range of tasks.
- `14` (distance 0.385195): Claim A: The parameter size of OPT models ranges from 125M to 175B. Claim B: The average model size used in these experiments is approximately 10 million parameters.
- `59` (distance 0.396451): Claim A: The noisy channel component increases the model's peak memory usage by an average of 20% across all benchmarked tasks. Claim B: The proposed method reduces the peak memory usage of LM inference by 8%.
- `60` (distance 0.363774): Claim A: Our analysis reveals that scaling the model capacity beyond 2 billion parameters incurs a 2% increase in inference latency. Claim B: With a 50% increase in model parameters, the inference time increases by 25% on the same dataset.
- `65` (distance 0.396343): Claim A: The average model size used in these experiments is approximately 10 million parameters. Claim B: The VeriTrace framework requires a model size of 120 million parameters, a 30% reduction from our baseline model.
- `86` (distance 0.405790): Claim A: The mean absolute difference in PSNR between our method and the baseline method is 1.05 dB on the standard test dataset. Claim B: Our proposed ORPQUANT achieves an average PSNR improvement of 1.2 dB over the baseline quantization method on the test set.
- `99` (distance 0.439573): Claim A: Training a 100M parameter transformer model on our proposed data augmentation technique improves accuracy by 2.5% on the GLUE dev set. Claim B: The scratchpad approach improves the accuracy of our models by at least 25% compared to standard transformer models.
- `121` (distance 0.449752): Claim A: The proposed method reduces the inference time by 22.1% while maintaining the same level of accuracy on the SQuAD v2.0 dataset. Claim B: With a 50% increase in model parameters, the inference time increases by 25% on the same dataset.
- `123` (distance 0.380770): Claim A: The proposed method achieves a relative model size reduction of 20% without compromising accuracy on the dataset used. Claim B: By increasing the model capacity from 50% to 2000% of the original size, the training dataset can be reduced by 30% without degrading the model's performance on the GRB 260310A dataset.

Not shown: `135`, `141`.

**B — 1 of 220 verified false positives still flagged (showing 1):**

- `171` (distance 0.340444): Claim A: By incorporating 7 additional reasoning steps, our model increases its F1 score by 18.2% on the MultiNLI benchmark. Claim B: We demonstrate that the proposed framework outperforms the baseline model on the F1-score metric by 10% on the test set.

**C:** none.

**D:** none.


### Pairwise differences and noise

| Metric | Comparison | A (95% CI) | B (95% CI) | Difference | CI overlap | Label |
|---|---|---|---|---:|---|---|
| Verified FP suppression (audit) | A vs B | 0.945 [0.907, 0.969] | 0.995 [0.975, 0.999] | -0.050 | disjoint | CIs disjoint |
| Verified FP suppression (audit) | A vs C | 0.945 [0.907, 0.969] | 1.000 [0.983, 1.000] | -0.055 | disjoint | CIs disjoint |
| Verified FP suppression (audit) | A vs D | 0.945 [0.907, 0.969] | 1.000 [0.983, 1.000] | -0.055 | disjoint | CIs disjoint |
| Verified FP suppression (audit) | B vs C | 0.995 [0.975, 0.999] | 1.000 [0.983, 1.000] | -0.005 | overlap | within noise |
| Verified FP suppression (audit) | B vs D | 0.995 [0.975, 0.999] | 1.000 [0.983, 1.000] | -0.005 | overlap | within noise |
| Verified FP suppression (audit) | C vs D | 1.000 [0.983, 1.000] | 1.000 [0.983, 1.000] | +0.000 | overlap | within noise |
| Verified TP retention (audit) | A vs B | 0.750 [0.301, 0.954] | 0.000 [0.000, 0.490] | +0.750 | overlap | within noise |
| Verified TP retention (audit) | A vs C | 0.750 [0.301, 0.954] | 0.250 [0.046, 0.699] | +0.500 | overlap | within noise |
| Verified TP retention (audit) | A vs D | 0.750 [0.301, 0.954] | 0.000 [0.000, 0.490] | +0.750 | overlap | within noise |
| Verified TP retention (audit) | B vs C | 0.000 [0.000, 0.490] | 0.250 [0.046, 0.699] | -0.250 | overlap | within noise |
| Verified TP retention (audit) | B vs D | 0.000 [0.000, 0.490] | 0.000 [0.000, 0.490] | +0.000 | overlap | within noise |
| Verified TP retention (audit) | C vs D | 0.250 [0.046, 0.699] | 0.000 [0.000, 0.490] | +0.250 | overlap | within noise |
| CONTRADICTS precision (full set) | A vs B | 0.200 [0.070, 0.452] | 0.000 [0.000, 0.793] | +0.200 | overlap | within noise |
| CONTRADICTS precision (full set) | A vs C | 0.200 [0.070, 0.452] | 1.000 [0.207, 1.000] | -0.800 | overlap | within noise |
| CONTRADICTS precision (full set) | A vs D | 0.200 [0.070, 0.452] | n/a | n/a | n/a | n/a |
| CONTRADICTS precision (full set) | B vs C | 0.000 [0.000, 0.793] | 1.000 [0.207, 1.000] | -1.000 | overlap | within noise |
| CONTRADICTS precision (full set) | B vs D | 0.000 [0.000, 0.793] | n/a | n/a | n/a | n/a |
| CONTRADICTS precision (full set) | C vs D | 1.000 [0.207, 1.000] | n/a | n/a | n/a | n/a |
| CONTRADICTS recall (full set) | A vs B | 0.750 [0.301, 0.954] | 0.000 [0.000, 0.490] | +0.750 | overlap | within noise |
| CONTRADICTS recall (full set) | A vs C | 0.750 [0.301, 0.954] | 0.250 [0.046, 0.699] | +0.500 | overlap | within noise |
| CONTRADICTS recall (full set) | A vs D | 0.750 [0.301, 0.954] | 0.000 [0.000, 0.490] | +0.750 | overlap | within noise |
| CONTRADICTS recall (full set) | B vs C | 0.000 [0.000, 0.490] | 0.250 [0.046, 0.699] | -0.250 | overlap | within noise |
| CONTRADICTS recall (full set) | B vs D | 0.000 [0.000, 0.490] | 0.000 [0.000, 0.490] | +0.000 | overlap | within noise |
| CONTRADICTS recall (full set) | C vs D | 0.250 [0.046, 0.699] | 0.000 [0.000, 0.490] | +0.250 | overlap | within noise |

`within noise` means the two Wilson 95% intervals overlap; this is descriptive, not a test.

### Interpretation

On the 224-pair audit, variant C stopped 220/220 verified false positives (suppression 1.000 [0.983, 1.000]) while keeping 1/4 confirmed contradictions (retention 0.250 [0.046, 0.699]); variant A kept 3/4 confirmed contradictions while stopping 208/220 verified false positives. On the 286-row evaluated full set, variant C flagged 1 pair with precision 1.000 [0.207, 1.000] and recall 0.250 [0.046, 0.699] (macro F1 0.514), and its 0.35 gate dropped 1/4 confirmed contradictions before the judge. With only 4 confirmed positives, 18 of 24 pairwise metric differences are marked within noise, so these are pilot signals rather than a stable ranking.

Reproduce with the command recorded in `judge_ablation.json`; the cache is `eval\results\ablation_cache.jsonl` and is keyed by `(variant, pair_id, signature)`.
