# Axion — Full System Guide (right now)

**Snapshot:** 2026-10-17 · `main` @ `c5afca9` · this file replaces the previous
point-in-time status report.

This is the operational guide to Axion **as it exists today**: what the system
is, what is in it, how to start it, verify it and troubleshoot it — and what is
honestly *not* true yet. It is written for whoever has to run or review the
system, not to sell it.

Companion documents:

| Document | Authoritative for |
| :--- | :--- |
| `PROJECT_INFO.md` | Full capability inventory, data model, product/technical limitations |
| `README.md` | User-facing overview, install steps, API and configuration reference |
| `progress.md` | Remediation tracker — every done/todo item with evidence |
| `eval/README.md` | Evaluation harness usage, dataset caveats, targets |
| **this file** | The system *right now*: run it, verify it, operate it |

---

## 1. What Axion is

Axion turns a set of research papers into a **queryable, connected map of what
they claim** — and where those claims conflict. It fetches papers from arXiv,
extracts atomic claims with provenance (section, evidence span, structured
fields), stores them in a graph (Neo4j) and a vector index (ChromaDB), then uses
an LLM to judge which cross-paper claim pairs *support*, *contradict*, or are
*unrelated* to each other. From that graph it derives research gaps,
contradiction-resolving experiment proposals, consensus evolution over time, and
citation-weighted confidence.

Two things make it more than a document Q&A bot: everything is **claim-level with
provenance**, and the headline workflow is **contradiction-first** — surface the
conflict, explain it, and propose the minimal experiment that would settle it.

**Honest posture:** the pipeline works end to end and is deployed, tested and
authenticated; the statistics of the contradiction classifier are *not* yet
trustworthy (see §11), and the system is a self-hosted prototype, not a
multi-tenant product (§13).

---

## 2. Right-now snapshot (verified 2026-10-17)

| Area | State |
| :--- | :--- |
| **Live corpus** | 48 papers · 2,389 claims · 2,389 vectors · 224 `CONTRADICTS` · 132 `SUPPORTS` · 93 `RELATED_TO` · 18 gaps · 36 experiment designs |
| **Stack** | 5 containers (`neo4j`, `redis`, `api`, `worker`, `web`), all healthy |
| **API** | 23 routes (22 under `/api` + `/healthz`), OpenAPI at `/docs` |
| **Auth** | Shared `AXION_API_KEY` on every write/compute route **and** job polling; fail-closed |
| **Background work** | Durable RQ + Redis queue, separate `worker` process; `202` + `GET /api/jobs/{id}`; cross-process verified |
| **LLM chain** | `groq` (`openai/gpt-oss-20b`) → `gemini` (`gemini-3.8-flash`, thinking disabled); Claude available, not in the chain |
| **Tests** | **229 passed / 12 deselected** offline; integration suite needs live services; CI on every push |
| **Frontend** | Next.js 16.2.6 (standalone), React 19, TS 5.7, Tailwind v4; `pnpm lint` 0 errors (2 known warnings) |
| **Eval** | `axion_pairs.csv` (286 pairs: 4/11/271); baselines recorded; retrieval gate measured; **post-change LLM run blocked on quota** |
| **Blocker** | `GROQ_API_KEY` / `GEMINI_API_KEY` must be reissued — both free tiers are exhausted (200k tokens/day Groq; 20 requests/day Gemini) |

---

## 3. Start it

### 3.1 Docker Compose — the supported path

```bash
cp .env.example .env          # then fill in the values below
docker compose up -d --build  # build both images and start all five services
docker compose ps             # expect: neo4j/redis/api/web healthy, worker up
```

Required in `.env` before first start:

| Variable | Why |
| :--- | :--- |
| `NEO4J_PASSWORD` | Neo4j refuses to start without it |
| `AXION_API_KEY` | Write/compute routes fail **closed** (503) without it |
| `GROQ_API_KEY` and/or `GEMINI_API_KEY` | Without one, ingestion and queries fail on the first LLM call |

Endpoints once up: API `http://localhost:8000` (`/docs` for OpenAPI), web UI
`http://localhost:3000`, Neo4j Browser `http://localhost:7474` (bolt `7887`),
Redis `127.0.0.1:6389`. Neo4j and Redis are loopback-bound; the API and web are
published on all interfaces.

Frontend notes: `NEXT_PUBLIC_API_URL` is baked in at **build** time; changing it
needs `docker compose build web`. The web server also needs its own
`AXION_API_URL=http://api:8000` and `AXION_API_KEY` (both set by Compose from the
root `.env`) so its server-side proxy can attach the key.

### 3.2 Local development (no Docker)

```bash
python -m venv venv && venv\Scripts\activate      # Windows
pip install -r requirements.txt -r requirements-dev.txt
docker compose up -d neo4j redis                  # datastores only
python -m uvicorn api.main:app --reload --port 8000
cd axion && pnpm install && pnpm dev              # separate terminal
```

Optional: `python -m jobs.worker` in a third terminal to consume queued jobs
locally. On Windows the worker automatically uses RQ's `SimpleWorker` (no
`os.fork`), so per-job timeouts are not enforced there. Without `REDIS_URL` the
API runs all jobs in-process instead — fine for development, but jobs are then
lost on restart and invisible to other processes.

### 3.3 CLI — batch operations

```bash
python main.py --mode ingest --query "chain of thought prompting" --n 10
python main.py --mode contradict     # judge claim pairs + recalc confidence
python main.py --mode gaps           # discover research gaps
python main.py --mode experiments    # design experiments for contradictions
python main.py --mode query          # run a coordinator query from the shell
python main.py --mode confidence     # recompute confidence
python main.py --mode citations      # refresh citation weights
python main.py --mode schedule       # run one scheduler cycle in the foreground
python main.py --mode backup         # Neo4j backup (host-side, shells out to Docker)
```

### 3.4 Verify the deployment

```bash
python scripts/queue_smoke.py     # auth on job routes + submits a query, reports
                                  # whether the worker claims it (queued -> running)
python eval/measure_gate.py       # offline: replays the retrieval gate over the
                                  # live vector index; no LLM, no writes
pytest                            # the offline suite (229 tests)
```

The smoke script needs the API key (reads `AXION_API_KEY` or the repo-root
`.env`) and submits a **real** query, so it consumes LLM quota.

---

## 4. Architecture

### 4.1 Services (docker-compose.yml, project `axion`)

| Service | Image | Port(s) | Role |
| :--- | :--- | :--- | :--- |
| `neo4j` | `neo4j:5.18-community` | `127.0.0.1:7887` bolt, `7474` browser | Graph store; APOC enabled; schema initialised on boot |
| `redis` | `redis:7.4-alpine` | `127.0.0.1:6389` | Durable job registry + queue + cross-process progress mirror |
| `api` | root `Dockerfile` | `8000` | FastAPI, single Uvicorn worker, reads/writes the graph, enqueues jobs, every request path except heavy work |
| `worker` | same image as `api` | — | `python -m jobs.worker`; executes ingestion and research-query jobs |
| `web` | `axion/Dockerfile` | `3000` | Next.js standalone UI + server-side proxy that holds the API key |

State lives outside the containers: Neo4j in the `neo4j_data` volume, ChromaDB
vectors and downloaded PDFs in the bind-mounted `./data`, and Hugging Face model
weights in the `hf_cache` volume. Job state lives in Redis (TTL-bounded).

> ChromaDB is opened by two processes (API reads, worker writes) over `./data`.
> SQLite/WAL handles that, but keep the **worker at 1 replica** while
> `SCHEDULER_ENABLED=true`, and treat the graph as the source of truth.

### 4.2 One ingestion cycle, step by step

1. **Fetch** (`ingestion/arxiv_client.py`) — topic search on arXiv, PDF download
   with retry/backoff.
2. **Parse** (`ingestion/pdf_parser.py`) — text extraction, section split,
   chunking (800 chars, 100 overlap).
3. **Chunk embeddings** — `paper_chunks` collection in ChromaDB.
4. **Extract claims** (`agents/reader.py`, LLM, ≤ 8 per section, ≥ 20 chars) —
   structured claim + evidence span + section, persisted to Neo4j with
   `EXTRACTED_FROM`, and embedded into the `claims` collection.
5. **Retrieve candidates** (`embeddings/store.py`) — top-8 nearest claims by
   cosine distance; same-paper and same-claim pairs are skipped, and only pairs
   within `CONTRADICTION_MAX_DISTANCE` (0.35) reach the judge.
6. **Judge** (`agents/contradiction.py`, LLM + deterministic guard) — returns
   `CONTRADICTS` / `SUPPORTS` / `UNRELATED` with an explanation, confidence, and a
   three-part decomposition; a `CONTRADICTS` verdict is **demoted** unless all
   three decomposition flags are true.
7. **Persist relationships** — non-`UNRELATED` verdicts become `CONTRADICTS` /
   `SUPPORTS` edges in Neo4j.
8. **Gaps** (`agents/gap_finder.py`, LLM) — open questions from future-work and
   limitation sections, linked to claims by `RELATED_TO`.
9. **Experiments** (`agents/experiment_recommender.py`, LLM) — a minimal
   experiment design stored as JSON on the contradiction edge.
10. **Confidence** (`agents/confidence_updater.py`) — heuristic propagation
    (`base + 0.08·supports − 0.12·contradictions`).

A **research query** (Coordinator v2) plans → retrieves → reflects (≤ 3
iterations) → synthesises a cited report; it runs as a queued job, never inside
the HTTP request.

### 4.3 Component map

| Component | Path | Responsibility | LLM? |
| :--- | :--- | :--- | :--: |
| arXiv client | `ingestion/arxiv_client.py` | topic search, PDF download | ❌ |
| PDF parser | `ingestion/pdf_parser.py` | text, sections, chunks | ❌ |
| Scheduler | `ingestion/scheduler.py` | periodic/custom ingestion; **enqueues** when a queue exists | ❌ |
| Progress tracker | `ingestion/progress.py` | status + logs for the UI, mirrored via Redis | ❌ |
| Reader | `agents/reader.py` | structured claim extraction + provenance | ✅ |
| Contradiction agent | `agents/contradiction.py` | candidate gate + relationship adjudication + demotion guard | ✅ |
| Gap finder | `agents/gap_finder.py` | gaps from future work + claim clusters | ✅ |
| Experiment recommender | `agents/experiment_recommender.py` | minimal resolving-experiment design | ✅ |
| Confidence updater | `agents/confidence_updater.py` | heuristic propagation | ❌ |
| Temporal agent | `agents/temporal.py` | consensus evolution, dispute timelines | ✅ |
| Citation agent | `agents/citation.py` | Semantic Scholar counts + weighting helper | ❌ |
| Coordinator v2 | `agents/coordinator_v2.py` (+ planner/reflector/synthesizer) | multi-step question answering | ✅ |
| Graph layer | `graph/neo4j_client.py`, `neo4j_queries.py`, `neo4j_schema.py` | driver, Cypher, schema | ❌ |
| Vector layer | `embeddings/store.py` | `claims` + `paper_chunks` collections | ❌ |
| Job queue | `jobs/` (`backend`, `store`, `tasks`, `worker`, `redis_conn`) | durable queue + worker, in-process fallback | ❌ |
| LLM router | `llm.py` | provider chain, retries, cooldown, optional cache | — |
| API | `api/main.py`, `api/models.py` | 22 `/api` routes + `/healthz` | — |
| Frontend | `axion/` | six-view workspace + server-side proxy | — |

---

## 5. Data model

### 5.1 Neo4j (graph store)

- **Nodes:** `Paper` (unique `arxiv_id`), `Claim` (unique `claim_id`),
  `Gap` (unique `gap_id`); `Benchmark` / `Dataset` / `Method` constraints exist
  but **no code populates those nodes**.
- **Edges:** `EXTRACTED_FROM` (claim → paper), `CONTRADICTS`, `SUPPORTS`,
  `RELATED_TO` (claim ↔ claim / gap).
- **Claim properties:** text, `section`, `evidence_span`, `base_confidence`,
  `confidence`, `paper_year`, structured fields (`subject`, `metric`,
  `direction`, …), and provenance links.
- **Experiment designs** are stored as JSON on the `CONTRADICTS` edge, not as
  separate nodes.
- Indexes cover year, section, confidence, subject, metric and direction.
- Schema is created idempotently at startup (`graph/neo4j_schema.py`).

### 5.2 Redis (queue + shared job state)

| Key | Contents |
| :--- | :--- |
| `rq:queue:axion` | pending jobs (RQ) |
| `axion:job:<id>` | job record: `{id, kind, status, created_at, started_at, finished_at, result, error}` |
| `axion:jobs:index` | ZSET of job ids by creation time |
| ingestion progress keys | the UI progress mirror |

Job records expire after `JOB_TTL_SECONDS` (default 1 day). The API and the
worker share this state, which is why job polling survives an API restart.

### 5.3 ChromaDB (vector store) and files

- `claims` — one 384-dim embedding per claim (`all-MiniLM-L6-v2`, computed locally).
- `paper_chunks` — section chunks used for retrieval during synthesis.
- `data/papers/` downloaded PDFs · `data/db/chroma/` vector store ·
  `data/backups/` Neo4j backups.

---

## 6. API surface

Base URL `http://localhost:8000`. OpenAPI: `/docs`, `/redoc`, `/openapi.json`.
🔑 = requires `X-API-Key: <AXION_API_KEY>`; if the key is unset the route
returns **503** (fail-closed), and a wrong/missing key returns **401**. The
legacy `X-Trigger-Secret` header is still accepted on the ingestion triggers.
Global rate limit 60/min per IP, with tighter per-route limits below.

| Method | Path | Purpose | Auth | Limit |
| :--- | :--- | :--- | :--: | :--- |
| GET | `/healthz` | liveness; always 200 while serving | — | — |
| GET | `/api/health` | readiness; 503 if Neo4j/Chroma unreachable | — | — |
| GET | `/api/metrics` | in-memory metrics summary | — | — |
| GET | `/api/stats` | graph counts | — | — |
| GET | `/api/claims` | list claims (`limit`, `offset`) | — | — |
| GET | `/api/claims/{id}/provenance` | full provenance chain for a claim | — | — |
| GET | `/api/contradictions` | contradictions (`min_confidence`, `limit`) | — | — |
| GET | `/api/experiments/{contradiction_id}` | stored experiment design | — | — |
| POST | `/api/experiments/{contradiction_id}/design` | design + store an experiment | 🔑 | 5/min |
| GET | `/api/gaps` | gaps (`?source=`) | — | — |
| POST | `/api/query` | **enqueue** a research query → `202 {job_id}` | 🔑 | 10/min |
| GET | `/api/jobs` | recent jobs, newest first (`limit` ≤ 100) | 🔑 | — |
| GET | `/api/jobs/{job_id}` | job status + result | 🔑 | — |
| GET | `/api/temporal/evolution` | consensus evolution (`topic`, years) | — | — |
| GET | `/api/temporal/disputes` | dispute timeline (`topic`) | — | — |
| GET | `/api/confidence/distribution` | confidence histogram | — | — |
| GET | `/api/confidence/most-changed` | biggest confidence moves | — | — |
| POST | `/api/confidence/recalculate` | recompute confidence for all claims | 🔑 | 2/min |
| GET | `/api/ingestion/status` | last run + running flag (queue-aware) | — | — |
| GET | `/api/ingestion/progress` | live progress + logs (Redis-mirrored) | — | — |
| POST | `/api/ingestion/trigger` | **enqueue** one ingestion cycle → `202` | 🔑 | 2/min |
| POST | `/api/ingestion/custom` | **enqueue** `{topic, limit}` (1–50) → `202` | 🔑 | 5/min |
| GET | `/api/graph` | nodes/edges for the graph canvas | — | — |

The frontend never sees the key. Write/compute calls go through the Next.js
route handler `axion/app/api/backend/[...path]/route.ts`, which matches an
explicit **method + path allowlist** (5 POST patterns + `GET jobs/{id}`),
attaches the key server-side, and returns 404 for anything else — so it cannot
be used as an open proxy. Read-only endpoints are called directly from the
browser.

---

## 7. Background jobs — the contract

Every long operation is a job. The request returns immediately; the client polls.

```bash
# submit (also used by ingestion triggers)
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" -H "X-API-Key: $AXION_API_KEY" \
  -d '{"question": "Do larger models benefit more from chain-of-thought prompting?"}'
# -> {"job_id":"...","status":"queued","backend":"rq"}

# poll
curl http://localhost:8000/api/jobs/<job_id> -H "X-API-Key: $AXION_API_KEY"
# -> {"id","kind","status","created_at","started_at","finished_at","result","error","backend"}
```

- `status` ∈ `queued` · `running` · `completed` · `failed`.
- **Two backends, one contract:** `backend: "rq"` when `REDIS_URL` is set (jobs
  are durable and executed by the worker process); `backend: "inline"` otherwise
  (thread pool in the API process — development only).
- **Failure text is sanitized:** clients see
  `"Job failed. Check the server logs for details."`; the full exception is
  logged (`docker compose logs worker`).
- **Ingestion exclusivity:** the scheduler enqueues instead of running, and
  `active_ingestion_job()` reads the shared registry, so a second ingestion
  request gets `409` while one is active — across processes.
- **Retries:** RQ re-queues a job whose worker was killed mid-flight; a job
  killed while `running` is retried when a worker returns.
- **Timeouts:** `JOB_TIMEOUT_SECONDS` (1800) is handed to RQ; per-job timeout
  enforcement requires `os.fork` (Linux containers), not Windows `SimpleWorker`.
- Internal `_payload` is stripped from every API response (`public_view`), so job
  polling cannot leak the submitted question payload beyond the job's own result.

---

## 8. LLM layer

| Setting | Value today |
| :--- | :--- |
| Chain | `["groq", "gemini"]` (Claude is configured but not in the chain) |
| Groq model | `openai/gpt-oss-20b` (reasoning models run with `reasoning_effort=low`) |
| Gemini model | `gemini-3.8-flash` with `GEMINI_THINKING_BUDGET=0` (Gemini 3.x otherwise burns ~110–130 hidden thought tokens per call) |
| Transient errors | retried on a short schedule (2 s / 5 s / 10 s) |
| Rate limits | fall through to the next provider |
| Hard failures | provider is **benched** for `LLM_PROVIDER_COOLDOWN_SECONDS` (300 s), so a dead provider does not cost retry time on every call |
| Cache | optional in-process `LLM_CACHE_ENABLED` (default off) |
| Observable via | `/api/metrics` (calls, tokens, timings) and structured logs |

If **every** provider is unavailable the chain raises
`All LLM providers exhausted after retries. Chain tried: [...]` → the job fails
cleanly and the error is logged. That is exactly what happens today, because
both free-tier quotas are exhausted (§2).

---

## 9. Configuration

All of it comes from `.env` (loaded by `config.py`). The values that matter:

| Variable | Default | Meaning |
| :--- | :--- | :--- |
| `NEO4J_URI` / `NEO4J_USERNAME` / `NEO4J_PASSWORD` | `bolt://localhost:7887` / `neo4j` / — | graph connection (password required) |
| `GROQ_API_KEY` / `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` | — | LLM credentials |
| `GEMINI_MODEL` / `GEMINI_THINKING_BUDGET` | `gemini-3.8-flash` / `0` | Gemini model + thinking budget |
| `LLM_PROVIDER_COOLDOWN_SECONDS` | `300` | provider bench time after a hard failure |
| `LLM_CACHE_ENABLED` | `false` | in-process response cache |
| `AXION_API_KEY` | — (fail-closed) | shared secret for write/compute **and** job routes |
| `TRIGGER_SECRET` | — | legacy `X-Trigger-Secret` alias |
| `REDIS_URL` | — (⇒ in-process jobs) | queue + shared job state (Compose sets the bundled Redis) |
| `JOB_TTL_SECONDS` / `JOB_TIMEOUT_SECONDS` | `86400` / `1800` | job retention / job timeout |
| `CONTRADICTION_MAX_DISTANCE` | `0.35` | max cosine distance that reaches the LLM judge |
| `SCHEDULER_ENABLED` / `SCHEDULER_INTERVAL_HOURS` / `SCHEDULER_PAPERS_PER_RUN` | `false` / `6` / `5` | periodic ingestion in the API process (single process only) |
| `ALLOWED_ORIGINS` | `http://localhost:3000,http://localhost:5173` | CORS allow-list |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | browser → API base (build-time, public) |
| `AXION_API_URL` | `http://localhost:8000` | web server → API base (runtime, e.g. `http://api:8000` in Compose) |
| `LOG_LEVEL` / `LOG_FORMAT` | `INFO` / `text` | logging |

Non-env constants in `config.py`: embedding model `all-MiniLM-L6-v2`,
`CHUNK_SIZE=800`, `CHUNK_OVERLAP=100`, `MAX_CLAIMS_PER_PAPER=8`,
`GROQ_MODEL=openai/gpt-oss-20b`, the scheduler topics (all LLM-related).

---

## 10. Testing and CI

```bash
pytest                  # offline suite: 229 passed, 12 deselected (no services needed)
pytest -m integration   # opt-in: needs live Neo4j + ChromaDB (and sometimes LLM)
pytest tests/test_jobs.py -q          # queue + worker policy
pytest tests/test_llm_router.py -q    # provider fallback, cooldown, retries
cd axion; pnpm lint; pnpm build       # frontend: 0 lint errors, type-checked build
```

CI (`.github/workflows/ci.yml`) runs the offline backend suite and a frontend
production build on every push/PR to `main`. Coverage is not measured.

What is **not** covered: view-level frontend tests, a load/soak test, and any
test that needs real provider quota.

---

## 11. Evaluation state (the honest version)

Two different questions, two different answers:

**Retrieval — measured, deterministic.** `eval/measure_gate.py` replays the
production top-8 search over all 2,389 claims (11,602 unique pairs):

| Gate | Pairs sent to the judge | Claims with a candidate |
| ---: | ---: | ---: |
| `0.95` (previous) | **100 %** — the gate was inert | 100 % |
| `0.35` (current) | **42.6 %** (57.4 % fewer judge calls) | 80.2 % |

Pair distances: min 0.000, p50 0.379, p90 0.538, p99 0.652, max 0.769.

**Judging — not measured on the new prompt.** `eval/Data/axion_pairs.csv`
(286 reviewed cross-paper pairs: 4 `CONTRADICTS` / 11 `SUPPORTS` / 271
`UNRELATED`) with these recorded baselines:

| Predictor | Accuracy | Macro F1 | `CONTRADICTS` P / R |
| :--- | ---: | ---: | ---: |
| majority (all `UNRELATED`) | 0.9476 | 0.3244 | 0.00 / 0.00 |
| random (fixed seed) | 0.3706 | 0.2191 | 0.13 / 0.38 |
| LLM (prefix baseline, pre-change prompt) | 0.8427 | 0.4822 | 0.15 / 0.50 |

The re-run against the **new prompt + demotion guard** died at pair 10/286 when
both free tiers ran out (Groq 200k tokens/day; Gemini 20 `gemini-3.8-flash`
requests/day). No post-change metric is claimed anywhere in this repository. The
fixes are covered by unit tests and a 6-pair hand-built probe (6/6 agreement),
which is *not* a benchmark. The human audit of the existing graph found only
**4 of 224** auto-detected contradictions to be real (~1.8 % precision) — that
number is why the gate and prompt work happened.

To finish this: reissue the two LLM keys, expand the reviewed `CONTRADICTS` set
(4 positives cannot support a precision claim), then run
`python eval/run_eval.py --predictor llm --dataset axion_pairs.csv`.

---

## 12. Security posture

- **Shared-key auth**, not accounts. One `AXION_API_KEY` gates everything that
  spends tokens, mutates the graph, or returns job results; it fails closed.
- **The key stays server-side.** It is held by the Next.js server and injected
  by the proxy route; it is never part of the browser bundle. Verified: no secret
  in any served JS chunk.
- **Datastores are loopback-bound** (Neo4j, Redis). The API and web UI are not.
- **Errors are generic** to clients and detailed in logs.
- **Rotations done:** `AXION_API_KEY`, `TRIGGER_SECRET`, Neo4j password.
  **Outstanding:** `GROQ_API_KEY` and `GEMINI_API_KEY` must be reissued (they
  were exposed in a config dump and are currently rate-capped anyway).
- **Not present:** TLS/reverse proxy, per-user identity, quotas, secret manager,
  scheduled backups, APOC restriction.

Do not expose this stack to an untrusted network as-is.

---

## 13. What is not true yet (do not claim it)

1. **No trustworthy contradiction-quality number.** The new prompt's precision
   and recall are unmeasured (§11); only the retrieval gate is measured.
2. **No per-user auth or multi-tenancy.** One shared key, no accounts, roles, or
   quotas.
3. **No production deployment story.** Plain HTTP, no reverse proxy, no domain,
   backups are manual and host-side.
4. **No durable metrics/observability.** `/api/metrics` resets on restart; no
   tracing, alerting or persistent store.
5. **Single-process ingestion.** The scheduler and metrics are process-local; the
   worker must stay at 1 replica while the scheduler is enabled.
6. **No human-in-the-loop correction** — nothing can be accepted, rejected or
   edited from the UI, and no feedback reaches the system.
7. **Feature gaps:** no export (PDF/Markdown/CSV), no notifications, no
   collaboration, no mobile/offline mode, no multilingual support, query history
   is browser-local, gaps carry no stored confidence.
8. **Coverage is ML/LLM-flavoured** (the default scheduler topics are all
   LLM-related); no domain guarantees.
9. **No migration framework** — schema changes are ad-hoc scripts.
10. **Live LLM features are down until keys are reissued** (quota exhausted).

---

## 14. Troubleshooting

| Symptom | Check |
| :--- | :--- |
| Compute routes return **503** | `AXION_API_KEY` unset on the server — it fails closed by design |
| Compute routes return **401** in the UI | The web server's `AXION_API_KEY` differs from the API's |
| Jobs stay **queued** forever | `docker compose logs worker` — it needs `REDIS_URL` and prints `*** Listening on axion`; run `python scripts/queue_smoke.py` |
| A job is **running** but never finishes | LLM retries/cooldowns; with every provider dead it fails after several minutes. Check `docker compose logs worker` for the real error |
| Query returns a generic failure | The full exception is only in the worker logs (client text is sanitized on purpose) |
| `/api/health` returns 503 | Neo4j or ChromaDB unreachable; check `docker compose ps` and `NEO4J_PASSWORD` |
| Frontend cannot reach the API | `NEXT_PUBLIC_API_URL` is baked in at build time — rebuild the `web` image |
| `pytest` fails on collection | You're running integration tests without services; use plain `pytest` (they're deselected) |
| Port conflicts | Host ports in use: 7887, 7474, 8000, 6389, 3000 |
| Worker crash-loops with `'str' object has no attribute 'decode'` | Fixed — upgrade past commit `82526c3` (the Redis client must run in bytes mode) |

---

## 15. Ownership of facts

If this file and another doc disagree, trust them in this order:
`PROJECT_INFO.md` (inventory) → `README.md` (usage) → this file (current
operation) → `progress.md` (history/checklist). Anything about evaluation
semantics and targets lives in `eval/README.md`.

Finally: the on-disk folder is still named `schimesh` while the project, the
GitHub repository and every artefact are **Axion**; the old
`scimesh_neo4j_data` volume still exists with data under the retired password
and should not be deleted without a decision.
