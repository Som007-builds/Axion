# PROGRESS.md — Axion Shipment Tracker

> Working tracker. NOT pushed to git (keep it untracked — do not `git add`).
> Created: 2026-10-16. Updated: 2026-10-16.
> Audit basis: full backend + frontend + tests/eval/ops/docs review of HEAD `0726da9`.

---

## Overall status

| Target | Estimate | State |
| :--- | :--- | :--- |
| Research / founder demo | ~1–2 weeks | **~85%** — core loop works, UI looks finished |
| Public self-hosted MVP | ~4–6 weeks | **~70–75%** — needs hardening, not features |
| Multi-tenant SaaS | 2–3+ months | **~40%** — auth, queue, observability, eval story missing |

**Bottom line:** ingestion → graph → reasoning → API → UI works end to end. Remaining work is correctness bugs, security, test/CI hygiene, eval, and deployment — not new features.

---

## 1. DONE

### Core system
- [x] ArXiv ingestion: search, PDF download, text extraction, section split (`ingestion/`)
- [x] LLM claim extraction with provenance stamping (`agents/reader.py`)
- [x] Neo4j persistence: Paper/Claim/Gap nodes, EXTRACTED_FROM/CONTRADICTS/SUPPORTS/RELATED_TO (`graph/`)
- [x] ChromaDB semantic retrieval, 2,389 vectors in sync with Neo4j (`embeddings/store.py`)
- [x] SQLite retired → full Neo4j migration (legacy archived in `archive/`)
- [x] Contradiction detection: similarity retrieval + LLM judgment + Neo4j writes (`agents/contradiction.py`)
- [x] Confidence propagation (`agents/confidence_updater.py`, endpoints + UI)
- [x] Gap discovery from future-work/limitation sections (`agents/gap_finder.py`)
- [x] Experiment recommender stored on contradiction edges (`agents/experiment_recommender.py`)
- [x] Temporal reasoning: year-filtered retrieval, consensus evolution, dispute timeline (`agents/temporal.py`)
- [x] Citation weighting via Semantic Scholar (`agents/citation.py`)
- [x] Coordinator v2: plan → retrieve → reflect (≤3 iters) → synthesize (`agents/coordinator_v2.py`, `planner/reflector/synthesizer`)
- [x] LLM provider chain with retry/backoff: groq → gemini, optional cache (`llm.py`)
- [x] FastAPI surface: all 20 functional endpoints wired (`api/main.py`) + `/healthz` liveness probe
- [x] Next.js workspace: 6 views (research, knowledge graph, contradictions, gaps, timeline, evolution) + ingestion sheet
- [x] Design system v2.0: dark shell, glass surfaces, skeletons, error/empty states, ⌘K, keyboard nav, canvas force graph
- [x] Persistent query history (localStorage), custom ingestion sheet, targeted contradiction checks
- [x] Logging, in-memory metrics, ingestion progress tracking, Neo4j backup utility
- [x] Pinned Python deps (all `==`), complete `.env.example`
- [x] 48 papers / 2,389 claims / 224 contradictions / 132 supports / 93 related / 30 gaps / 12 experiments ingested
- [x] 94 test functions written (~89 properly mocked unit tests)

---

## 2. BROKEN / FIX FIRST (P0) — ✅ DONE 2026-10-16

- [x] **`get_graph_stats` returned `{}` when gaps/contradictions were 0** → rewrote with Neo4j 5 `COUNT {...}` subqueries (always one row). `graph/neo4j_queries.py`.
- [x] **Temporal endpoints schema mismatch** → `/api/temporal/disputes` now maps `description/first_appeared/status/resolution/resolution_year/related_claim_ids`; evolution uses real per-year confidence (LLM) with top-level fallback and skips rows without a valid year. `api/main.py`, `api/models.py`, `agents/temporal.py` (prompt + data-driven year fallback + claim-id→text map).
- [x] **Secret check failed open** → now fail-closed: unset `TRIGGER_SECRET` returns 503, wrong/missing secret returns 401, constant-time compare (`secrets.compare_digest`). `api/main.py:require_trigger_secret`.
- [x] **Global exception handler leaked raw `str(exc)`** → now logs the traceback and returns `{"error":"Internal server error"}`. Also sanitized `/api/health` + `/api/metrics` error strings.
- [x] **Placeholder data removed**: gaps confidence now `null` (frontend guards), graph paper `year` read from Neo4j, contradictions now return real `section`/`arxiv_id`/per-claim `confidence` (extended `get_contradictions` query).
- [x] **API boots degraded** instead of crashing when Neo4j/Chroma are down (`/api/health` returns 503) — verified with TestClient.
- [x] **Config/port drift fixed**: defaults + `.env.example` now match compose (`7887`, `axion_neo4j`); compose publishes only `127.0.0.1`, added healthcheck, dropped obsolete `version:`.
- [x] **Local env wired** for the new fail-closed secret: generated secret appended to untracked `.env`, created `axion/.env.local` (both gitignored via new `.gitignore` rules).
- [ ] **Rotate secrets** — still open: live-format `GEMINI_API_KEY`, `GROQ_API_KEY` and weak `NEO4J_PASSWORD=scimesh123` sit in untracked `.env`. Rotate + strengthen before any archive/zip/publish. (`NEXT_PUBLIC_TRIGGER_SECRET` is inherently public — move triggers behind real auth before multi-user.)

### P0 test hygiene — ✅ DONE 2026-10-16
- [x] `tests/test_claims.py` no longer breaks collection (rewritten as an `integration` test).
- [x] `test_rate_limit_retry` no longer leaks to a live Gemini call (chain pinned to `["groq"]`).
- [x] `pytest.ini` gained an `integration` marker; integration tests excluded by default.
- [x] `tests/test_neo4j.py` marked `integration`.
- [x] Added `tests/test_api_regressions.py` (8 tests) covering the P0 fixes.
- [x] **`pytest` now green offline: 142 passed, 12 deselected** (grew 97 → 111 via Tracks A/D, → 142 via Track C test conversions + new ingestion/HTTP tests).

---

## 3. TODO — by track

### A. Correctness / backend (P0–P1)
- [x] Start scheduler from the API — env-gated via `SCHEDULER_ENABLED` (default off), started/shut down in FastAPI startup/shutdown, with a single-worker warning. `.env.example` updated.
- [x] Accurate ingestion running state (`ingestion.scheduler.is_running()`, overlapping-run guard; `/api/ingestion/status` + custom-ingestion 409 now use it)
- [ ] Make ingestion state cross-process safe (in-memory `IngestionProgressTracker` + `is_running` are per-process → need Redis/DB or a real queue; current design is single-worker only)
- [ ] Offload blocking work: LLM `time.sleep` backoff up to 300s, citation 1.5s/request sleep, `/api/query` runs the full LLM loop inside the HTTP request
- [x] **Confirmed 2026-10-17 against live Neo4j 5.18** — `COUNT {}` returns papers 48 / claims 2,389 / contradictions 224 with no aggregation pitfalls.

### B. Security (P0–P1)
- [ ] Auth layer (none exists) — at minimum for `/api/query`, `/api/confidence/recalculate`, ingestion triggers
- [ ] Reject requests when trigger secret unset (P0 above)
- [ ] Tighten CORS review, publish Neo4j port only on localhost, restrict APOC
- [ ] Document secret-rotation policy

### C. Testing + CI (P1)
- [x] Make `pytest` pass offline (collection error fixed, provider-chain leak pinned, `integration` marker added)
- [x] Add `requirements-dev.txt` (pytest, pytest-cov, httpx) — keeps prod `requirements.txt` clean
- [x] Add first CI: `.github/workflows/ci.yml` (backend offline tests + frontend build)
- [x] Frontend type-checks clean; removed `typescript.ignoreBuildErrors` from `next.config.mjs`; `pnpm build` now enforces types
- [x] Converted `test_phase4.py` / `test_phase5.py` into real pytest tests — offline structural/config/mocked-planner checks run by default; live-service checks marked `integration`. (They previously collected **0** tests — silent no-ops.)
- [x] Frontend lint: added `eslint` + `eslint-config-next` (flat `eslint.config.mjs`) and wired `pnpm lint` into CI. `pnpm lint` is green (0 errors; 2 `react-hooks/set-state-in-effect` warnings for deliberate localStorage hydration). Also fixed the flagged issues: hydration-guard `setMounted` → `useIsClient()` (`useSyncExternalStore`), `executeQuery` accessed-before-declared, unused imports/vars, derived sheet-open state.
- [x] Broaden coverage: added `tests/test_ingestion.py` (13 tests — `chunk_text`, `extract_sections`, `IngestionProgressTracker`) and `tests/test_api_endpoints.py` (9 HTTP tests via `TestClient` — health/degraded, ingestion status/progress, trigger-secret over HTTP, metrics, lifespan boot). Suite: **142 passed, 12 deselected**.
- [x] Pruned ~34 orphaned frontend deps left behind by the Track F component deletions (`@hookform/resolvers`, 20 unused Radix packages, `cmdk`, `recharts`, `sonner`, `vaul`, `next-themes`, `zod`, …) and regenerated `pnpm-lock.yaml`.
- [x] Refactored FastAPI `@app.on_event` startup/shutdown → `lifespan` context manager (removes the deprecation warnings; behaviour unchanged, scheduler still env-gated).

### D. Evaluation (P1–P2)
- [x] **Implemented `eval/run_eval.py`** — single entry point (`--predictor majority|random|llm`, `--dataset`, `--limit`, `--seed`, `--include-same-paper`) with shared `eval/metrics.py`, `eval/dataset.py`, `eval/predictors.py`. `baseline_llm_eval.py` is now a delegating shim.
- [x] Fixed path handling: harness resolves `eval/Data` relative to the file; fixed lowercase `eval/data` in 4 data-prep scripts (broke on Linux/CI).
- [x] Added `numpy`/`pandas`/`scikit-learn` to `requirements-dev.txt`; added `eval/README.md` with usage, targets, and dataset caveats.
- [x] Added `tests/test_eval_metrics.py` (13 hermetic tests) so CI exercises the harness offline.
- [x] Honest diagnostics: harness now reports class mix, same-paper exclusions, and `warnings` when a class has no support / the run is single-class.
- [ ] **BLOCKED — dataset is not fit for purpose.** Every SUPPORTS/CONTRADICTS label in train/val/test is a *same-paper* pair, which `check_pair` refuses to score. Production-aligned eval (`--include-same-paper` off) leaves the test split 100% UNRELATED → majority baseline scores acc 1.0 / macro F1 0.33. Needs a rebuilt eval set of **cross-paper** pairs with real positive labels.
- [ ] **BLOCKED — `eval/Data/Labeled_pairs.csv` is 0 bytes** (collides with lowercase `labeled_pairs.csv` on Windows), so `split_dataset.py` can no longer regenerate train/val/test. Recover or recreate the source labels.
- [ ] Re-run the real LLM baseline once valid data exists; then retire `eval/results/baseline_llm.json` (2026-08-02, wrong denominator). Reference baseline `eval/results/majority_test.json` recorded instead.
- [ ] `eval/Data/labeled_pairs_cleaned.csv` is 100% UNRELATED (68 rows) — do not use as an eval set.
- [x] Decision: **drop** the empty `eval/models/` + `eval/classifier/` plan (never populated; documented in `eval/README.md`).
- [ ] Add retrieval-level + agent-level eval (not just pair classification)
- [ ] Instrument `check_pair` so JSON parse failures are distinguishable from genuine UNRELATED verdicts

### E. Deployment / ops (P2)
- [x] **Dockerized + full-stack compose — DONE 2026-10-16.** Root `Dockerfile` (python:3.11-slim, CPU-only torch, pinned deps, `/healthz` healthcheck, single worker); `axion/Dockerfile` (multi-stage Node 20 + pnpm, Next.js `output: "standalone"`, non-root, healthcheck); `docker-compose.yml` now `neo4j` + `api` + `web` (health-gated startup, `./data` bind mount, `hf_cache` volume, `.env` interpolation, project name `axion`); `.dockerignore` (root + frontend). Added `GET /healthz` liveness (distinct from readiness `/api/health`). Validated: `docker compose config` parses, frontend standalone bundle builds. `next.config.mjs` gained `output: "standalone"`.
- [x] **Verified end-to-end 2026-10-17 (Docker 29.4.3).** Both images build; `docker compose up` brings neo4j+api+web to healthy; the containerized API serves the real graph (papers 48 / claims 2,389 / contradictions 224) and web returns 200. Three deployment-breaking defects found and fixed: (1) frontend image failed `ERR_PNPM_LOCKFILE_CONFIG_MISMATCH` — Corepack pulled pnpm 12, which ignores `pnpm.overrides`; pinned `packageManager: pnpm@10.22.0`; (2) `NEO4J_PASSWORD` on the neo4j container was parsed as a config setting → startup crash; the healthcheck now derives the password from `NEO4J_AUTH`; (3) `arxiv` was missing from `requirements.txt` → `/api/ingestion/status` returned 500 in-container. Integration suite: 12 passed against live services.
- [ ] Durable task queue (README already plans Celery/RQ)
- [ ] Persistent metrics/tracing/alerting (currently in-memory only)
- [ ] Data validation + migration discipline (retire ad-hoc `graph/migrate_*.py`, `fix_*.py`)
- [ ] Reproducible env: Python version marker, hash pinning, tracked eval data
- [ ] Reverse proxy / TLS / domain; automate Neo4j backups in compose (backup util is host-only today)

### F. Frontend cleanup (P3)
- [ ] Dead API-client helpers: removed unused `getClaims`; `getHealth` still unused — wire it into the status bar or delete it
- [ ] Surface `/api/claims/{id}/provenance` and `/api/metrics` in UI (Phase 7 / Phase 9, never called)
- [x] Surface the real `GraphStats.experiments` count in the dashboard stats strip.
- [x] Replaced hardcoded "System Online" green dot (`nav-rail.tsx`) and "Neo4j Connected" inference (`status-bar.tsx`) with real `/api/health` probes.
- [x] Honest query loading state — removed the fake pipeline animation; loading is now indeterminate while `/api/query` runs.
- [x] Fixed `experiment-card.tsx` — the auto-fetch moved from the render body into a `useEffect` (starts in the loading state to avoid setState-in-effect).
- [x] Deleted dead code: 47 unused `components/ui/*`, orphaned `styles/globals.css`, `theme-provider.tsx`, duplicate hooks, placeholder `public/` assets.
- [x] Documented `NEXT_PUBLIC_API_URL` (and `NEXT_PUBLIC_TRIGGER_SECRET`) in `.env.example`.
- [x] Added `app/error.tsx`, `app/loading.tsx`, `app/not-found.tsx`; package renamed to `axion`.
      → package rename ✅ DONE; error/loading boundaries still open

### G. Docs / branding (P3) — ✅ MOSTLY DONE 2026-10-16
- [x] **Pick one name → AXION.** Renamed everywhere: `api/main.py`, `main.py`, `config.py` (DB path + container default), `embeddings/store.py`, `agents/synthesizer.py`, `archive/coordinator_v1.py`, `graph/migrate_to_neo4j.py`, `requirements.txt`, `axion/types/axion.ts`, `.env.example`, `docker-compose.yml` (container `axion_neo4j`), `data/db/scimesh.db`→`axion.db`, `tests/test_aethergraph.py`→`tests/test_axion.py`, README + all side docs.
- [x] Reconcile stats: README Live Stats now 48 / 2,389 / 224 / 132 / 30 / 12 (matches `PROJECT_INFO.md`). `PROJECT_STATUS_NOW.md` marked **SUPERSEDED**.
- [x] Docs of non-existent files: fixed `AXION_SPEC.md` tree — removed `ui/` and `graph/queries.py`, added `archive/`, `eval/`, `ingestion/`.
- [x] README CLI reference no longer lists unimplemented `--mode init/redteam/communities`; lists real modes only (+ `query`, `backup`).
- [x] Reconcile version labels: `requirements.txt` header now "Axion v2.30" (matches `AXION_SPEC.md`).
- [x] README **false claims removed**: deleted the non-existent "red-team agent" and the 6 contradiction types (code emits only `CONTRADICTS` / `SUPPORTS` / `UNRELATED`); fixed diagram, prerequisites (Python 3.11+/Node 20+), and Known Limitations.
- [x] Added `LICENSE` (MIT) — README claimed MIT but no LICENSE file existed.
- [x] Added status banners to the 6 side docs pointing at `PROJECT_INFO.md` as authoritative.
- [ ] **Commit the untracked docs** — `AI_CONTEXT.md`, `AXION_MASTER_CONTEXT.md`, `FILE_MAP.md`, `FRONTEND_HANDOVER.md`, `PROJECT_STATE.md`, `PROJECT_STATUS_NOW.md`, `PROJECT_INFO.md`, `LICENSE`, and `eval/` are still NOT in git (not committed this session by design — `progress.md`/`PROJECT_INFO.md` stay untracked)
- [ ] Repo **folder** still named `schimesh`; GitHub repo still `AetherGraph` — rename both out-of-band, then the README clone URL (`.../Axion`) will resolve

---

## 4. Sequencing (start here)

1. **P0 bugs** — stats, temporal, fail-open secret, error leak (visible wrong data + security)
2. **Offline-green tests + first CI** — fix `test_claims.py`, provider-chain leak, add markers
3. **Commit untracked docs + eval**, unify name to Axion, correct README stats
4. **Re-run eval** on real cleaned data, record honest numbers
5. ~~**Dockerize API + frontend**, fix port mismatch, boot degraded~~ ✅ done 2026-10-16
6. **Auth + task queue** before any multi-user use

---

## 5. Log

- `2026-10-16` — Tracker created from full codebase audit (backend / frontend / tests-eval-ops-docs).
- `2026-10-16` — **P0 pass complete**: stats/temporal bugs fixed, trigger secret fail-closed, error-leak sanitized, placeholders removed, API boots degraded, config/port drift fixed, offline `pytest` green (97 passed / 6 deselected), 8 regression tests added.
- `2026-10-16` — **P1 CI/type pass**: added `.github/workflows/ci.yml` + `requirements-dev.txt`; fixed all 4 pre-existing frontend type errors; removed `ignoreBuildErrors` (build now type-checks); renamed frontend package to `axion`. `pnpm build` + `tsc --noEmit` clean; `pytest` still green.
- `2026-10-16` — **Track A start**: API-started scheduler (`SCHEDULER_ENABLED`, shutdown handler, overlap guard), real ingestion running state, custom-ingestion 409 guard. Tests 100 passed / 6 deselected.
- `2026-10-16` — **Track D (eval)**: rewrote `eval/run_eval.py` + `metrics.py`/`dataset.py`/`predictors.py`; shimmed `baseline_llm_eval.py`; fixed `eval/data`→`eval/Data` case bugs; added `tests/test_eval_metrics.py`, `eval/README.md`, eval deps. **Finding: the labelled dataset cannot measure production behaviour** — all SUPPORTS/CONTRADICTS labels are same-paper pairs (which the agent refuses to score); default eval is 100% UNRELATED. Tests 111 passed / 6 deselected.
- `2026-10-16` — Decision: canonical project name is **Axion** (rename pass pending).
- `2026-10-16` — **Track E (deployment)**: added `Dockerfile` (API, CPU-only torch, single worker), `axion/Dockerfile` (Next.js standalone), full-stack `docker-compose.yml` (neo4j+api+web, health-gated), `.dockerignore` ×2, `/healthz` liveness endpoint, `output: "standalone"`. `docker compose config` validated; standalone build verified. Image build/run unverified (Docker daemon down).
- `2026-10-16` — **`PROJECT_INFO.md` written** (repo root, untracked): full technical + product inventory — capabilities, explicit limitations ("what it cannot do"), architecture, data model, 21-endpoint API reference, config reference, security posture, deployment, shipment-readiness, roadmap, glossary.
- `2026-10-17` — **Docker verification pass (Track E).** Started the daemon, built both images, brought neo4j+api+web up healthy, and confirmed the containerized API returns the real graph (48 / 2,389 / 224). Fixed three deployment-breaking bugs: pnpm version pin, Neo4j `NEO4J_PASSWORD` config collision, missing `arxiv` dependency. Commits: `72319f9` (tests + lint + lifespan), `e5af0a7` (Docker fixes). Open: live `/api/stats` reports gaps 18 / experiments 36 vs docs' 30 / 12 — reconcile.
