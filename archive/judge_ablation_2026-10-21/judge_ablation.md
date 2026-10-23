# Judge ablation — 2026-10-21

**Run status:** `partial`
**Note:** A/B/C complete. Groq runs were paced at 6.5s (C, B) and 4s (A) to stay under the 8k tokens/minute limit. A and B share the old prompt/model but disagreed on all three positives that passed both gates (0, 96, 215), so A-vs-B is one noisy sample, not a clean gate comparison. D is partial: Gemini 3.8 Flash returned 503 UNAVAILABLE on two attempts; 19 judged calls completed (141/286 rows).
**Rendering:** generated from cache; no provider calls were made in this step.

**Dataset:** `eval\Data\axion_pairs.csv` (286 rows: CONTRADICTS 4, SUPPORTS 11, UNRELATED 271)
**Rows:** 286 combined; 4 CONTRADICTS positives
**Embedding:** `all-MiniLM-L6-v2`; distance = 1 - cosine similarity, computed locally with sentence-transformers.
**Old prompt:** recovered from `82526c3^` (`ffc222a3ce27`), sha256 `4c7e1d55997e3432`.
**Current prompt:** `agents/contradiction.py`, sha256 `2a8e00957a001501`.

A/B use the old prompt; C/D use the current prompt. The configured primary model is `groq/openai/gpt-oss-20b`. D uses the stronger configured model `gemini/gemini-3.8-flash`. Provider fallback and retries are disabled so a quota error stops the run.

| Variant | Gate | Prompt / guard | Model | Evaluated | CONTRADICTS flagged | TP | Precision (95% CI) | Recall (95% CI) | Gate-dropped positives | Guard-demoted positives | Macro F1 | LLM calls | Tokens |
|---|---:|---|---|---:|---:|---:|---|---|---|---:|---:|---:|---:|
| A | 0.95 | old / off | groq/openai/gpt-oss-20b | 286/286 | 15 | 3 | 0.200 [0.070, 0.452] | 0.750 [0.301, 0.954] | 0 | 0 | 0.532 | 286 | 122950 |
| B | 0.35 | old / off | groq/openai/gpt-oss-20b | 286/286 | 1 | 0 | 0.000 [0.000, 0.793] | 0.000 [0.000, 0.490] | 1 (124) | 0 | 0.354 | 34 | 15261 |
| C | 0.35 | current / on | groq/openai/gpt-oss-20b | 286/286 | 1 | 1 | 1.000 [0.207, 1.000] | 0.250 [0.046, 0.699] | 1 (124) | 0 | 0.514 | 34 | 26402 |
| D | 0.35 | current / on | gemini/gemini-3.8-flash | 141/286 (partial) | 0 | 0 | n/a | 0.000 [0.000, 0.561] | 1 (124) | 0 | 0.419 | 19 | 12477 |

Precision and recall are proportions with Wilson 95% intervals; `n/a` means the denominator was zero. Gate-dropped positives are human CONTRADICTS pairs whose distance exceeded the variant gate and therefore never reached the judge. LLM calls counts judged pairs represented in the results; `calls_this_run` in the JSON is 0 when this report was rendered from cache.

## Known CONTRADICTS pairs

| Pair | Distance | A | B | C | D |
|---|---:|---|---|---|---|
| 0 | 0.180160 | CONTRADICTS | UNRELATED | UNRELATED | UNRELATED |
| 96 | 0.247491 | CONTRADICTS | UNRELATED | UNRELATED | UNRELATED |
| 124 | 0.501931 | CONTRADICTS | UNRELATED (gate) | UNRELATED (gate) | UNRELATED (gate) |
| 215 | 0.274785 | UNRELATED | SUPPORTS | CONTRADICTS | not run |

## Interpretation

A (old prompt, 0.95) flags 15 pairs and recovers 3/4 known contradictions (precision 0.200, recall 0.750); B (old prompt, 0.35) flags 1 and recovers 0/4, while C (current, 0.35) flags 1 and recovers 1/4; the guard demoted 0 raw CONTRADICTS in C. The 0.35 gate drops 1 of 4 evaluated known contradictions before the judge (B=1, C=1), whereas the old 0.95 gate drops 0 (A=0); of C's 3 missed positives, 1 is gate-dropped and 2 pass the gate but are judged UNRELATED, so the prompt is at least as large a recall cost as the gate. With only 4 positive pairs, the Wilson intervals are wide, so these differences are a pilot signal rather than a stable ranking; partial variants: D 141/286.

Reproduce with the command recorded in `judge_ablation.json`; the cache is `eval\results\ablation_cache.jsonl` and is keyed by `(variant, pair_id)`.
