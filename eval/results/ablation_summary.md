# Judge ablation summary — 2026-10-23

This summary is generated from `eval/results/judge_ablation.json`; the primary metric is the 224-row human audit (220 verified false positives, 4 confirmed contradictions). The full set has 286 reviewed rows.

## Headline comparison

| Variant | Configuration | CONTRADICTS flagged | TP | FP | Precision (95% CI) | TPs kept / 4 | FPs suppressed / 220 |
|---|---|---:|---:|---:|---|---:|---:|
| A | gate 0.95; old prompt; guard off; groq/openai/gpt-oss-20b | 15 | 3 | 12 | 0.200 [0.070, 0.452] | 3/4 | 208/220 |
| B | gate 0.35; old prompt; guard off; groq/openai/gpt-oss-20b | 1 | 0 | 1 | 0.000 [0.000, 0.793] | 0/4 | 219/220 |
| C | gate 0.35; current prompt; guard on; groq/openai/gpt-oss-20b | 1 | 1 | 0 | 1.000 [0.207, 1.000] | 1/4 | 220/220 |
| D | gate 0.35; current prompt; guard on; gemini/gemini-3.8-flash | 0 | 0 | 0 | n/a | 0/4 | 220/220 |

## What the numbers say

- C suppresses all 220 verified false positives but keeps only 1/4 confirmed contradictions; A keeps 3/4 but leaves 12 verified false positives.
- B keeps 0/4 and D keeps 0/4 confirmed contradictions. D flags nothing on the full set, so its precision is undefined; it is an alternative judge, not an assumed upgrade.
- The 0.35 gate drops pair 124 (distance 0.501931), one of only four confirmed contradictions, before B/C/D ever judge it; A keeps it.
- A and B use the same model and old prompt but agree on only 22/34 gate-passing pairs (0.647 [0.479, 0.785]); 12 verdicts flip, so a single run is not stable.
- Read this as preliminary pilot evidence: only 4 confirmed positives, one 286-row reviewed set, 62 rows from unverified negative provenance, and 18/24 pairwise comparisons within noise. A–C use the current `openai/gpt-oss-20b`; the original 1.8% production figure came from `llama-3.1-8b-instant` at gate 0.95 with the old prompt, so the model swap is unmeasured.

## Verbatim examples

Claim texts below are copied from `eval/Data/axion_pairs.csv`; pair outcomes are the final predictions in the cache.

### (a) Pair `123` — human label `UNRELATED`, distance `0.380770`

**Variant outcomes:** A `CONTRADICTS`; B `UNRELATED (gate)`; C `UNRELATED (gate)`; D `UNRELATED (gate)`.

> Claim A: The proposed method achieves a relative model size reduction of 20% without compromising accuracy on the dataset used.
>
> Claim B: By increasing the model capacity from 50% to 2000% of the original size, the training dataset can be reduced by 30% without degrading the model's performance on the GRB 260310A dataset.

A verified false positive that A flags and B/C/D suppress at the 0.35 gate. Both claims report preserving accuracy while reducing a resource; this is a same-result restatement, not a contradiction.

### (b) Pair `171` — human label `UNRELATED`, distance `0.340444`

**Variant outcomes:** A `UNRELATED`; B `CONTRADICTS`; C `UNRELATED`; D `UNRELATED`.

> Claim A: By incorporating 7 additional reasoning steps, our model increases its F1 score by 18.2% on the MultiNLI benchmark.
>
> Claim B: We demonstrate that the proposed framework outperforms the baseline model on the F1-score metric by 10% on the test set.

No verified false positive survives all four variants. This is the only verified false positive still flagged by B; A suppresses it, and C/D suppress all 220.

### (c) Pair `124` — human label `CONTRADICTS`, distance `0.501931`

**Variant outcomes:** A `CONTRADICTS`; B `UNRELATED (gate)`; C `UNRELATED (gate)`; D `UNRELATED (gate)`.

> Claim A: The 1.8B parameter LLM model outperforms the 1.5B parameter LLM model by 5.4% in accuracy on the GLUE benchmark, while the 2.5B parameter LLM model outperforms the 1.5B parameter LLM model by 10.9% in accuracy.
>
> Claim B: Model scale is not correlated with performance across 15 LLMs.

A confirmed contradiction dropped by the 0.35 gate before judging in B/C/D; A's 0.95 gate keeps it.

### (d) Pair `215` — human label `CONTRADICTS`, distance `0.274785`

**Variant outcomes:** A `UNRELATED`; B `SUPPORTS`; C `CONTRADICTS`; D `UNRELATED`.

> Claim A: Chain-of-thought prompting struggles with problems harder than those exemplified in the prompts on symbolic manipulation tasks.
>
> Claim B: Chain-of-thought prompting improves performance on arithmetic, commonsense, and symbolic reasoning tasks.

C is the only variant that keeps this confirmed contradiction.

## Read with care

- The audit has only four confirmed positives; precision and recall intervals are wide, and a one-pair difference can change the ranking.
- The full set includes 62 rows from `labeled_pairs_cleaned` with unverified negative provenance; the primary audit uses only the 224 human-reviewed rows.
- The pairwise labels are a descriptive Wilson-overlap screen, not a hypothesis test; 18 of 24 comparisons overlap.
- D changes both provider and model, so its result is not a clean estimate of model strength. A–C's current-model run is not the original production model.
