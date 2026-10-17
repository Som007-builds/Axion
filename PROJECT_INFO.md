# Axion — Full Project Information

> Reference document: what this project is, what it can do, what it **cannot**
> do, and every technical and product detail worth knowing.
>
> Last updated: **2026-10-16**
> Baseline commit: `0726da9` ("Update README.md project name to Axion") + the
> uncommitted work-in-progress described in `progress.md`.
> Companion docs: `progress.md` (actionable tracker), `eval/README.md` (eval
> details), `README.md`. This file is the authoritative inventory.

---

## 0. At a glance

| Field | Value |
| :--- | :--- |
| **Product name** | **Axion** (canonical; renamed repo-wide 2026-10-16). Formerly SciMesh / AetherGraph. |
| **Repository folder** | `schimesh` |
| **What it is** | A multi-agent research intelligence platform that ingests scientific papers, extracts claims, and builds a knowledge graph of contradictions, support, gaps, and temporal consensus shifts. |
| **Category** | AI research tooling / literature intelligence / knowledge graph |
| **Backend** | Python 3.11, FastAPI |
| **Frontend** | Next.js 16 (App Router, Turbopack), React 19, TypeScript, Tailwind v4 |
| **Datastores** | Neo4j 5.18 (graph), ChromaDB (vectors), filesystem (PDFs/backups) |
| **LLM providers** | Groq (primary), Google Gemini (fallback), Anthropic Claude (available, not in default chain) |
| **Embeddings** | `all-MiniLM-L6-v2` (384-dim) via sentence-transformers |
| **API endpoints** | 23 (22 under `/api` + `/healthz` liveness) |
| **UI surfaces** | 6 views + dashboard stats + ingestion sheet |
| **Tests** | 229 passing offline, 12 integration deselected |
| **Data (verified 2026-10-17)** | 48 papers · 2,389 claims · 224 contradictions · 132 supports · 93 related · 18 gaps · 36 experiments |
| **Demo readiness** | ~92% |
| **Product readiness** | ~50% (see §12) |
| **Licence** | MIT (`LICENSE`) |

---

## 1. Executive summary

Axion turns a pile of research papers into a **queryable, connected map of what
science currently claims** — and where those claims conflict.

The pipeline is: **fetch papers → extract structured claims with provenance →
store them in a graph + vector index → detect contradictions, support, and
research gaps → design experiments to resolve disputes → reason over the graph
to answer research questions → show it all in a web workspace.**

It is not a chatbot over PDFs. The core value is the *graph*: claims linked to
paper/section/evidence, contradictions linked to explanations and confidence,
gaps linked to the claims that imply them, and a temporal view of how consensus
changed year over year.

**Where it is today:** the full loop (ingest → graph → reason → API → UI) works
end to end on a real corpus. What remains is correctness hardening, security,
testing/CI discipline, a *valid* evaluation, and deployment — not new features.

---

## 2. Product overview

### 2.1 Problem it addresses

- Scientific literature is growing faster than any researcher can read.
- Contradictory findings are scattered across papers and rarely stated side by side.
- Knowing "what does the field agree on, what is disputed, and what is untested" requires weeks of manual synthesis.
- Evidence is often lost: a claim is quoted without its paper, section, or sentence.

### 2.2 What Axion is

A self-hosted web application + automated pipeline that:

1. **Ingests** arXiv papers (search by topic, download PDF, extract text).
2. **Extracts** atomic, structured claims (subject / metric / direction / confidence / evidence span / section).
3. **Connects** claims into a Neo4j knowledge graph (`CONTRADICTS`, `SUPPORTS`, `RELATED_TO`, `EXTRACTED_FROM`).
4. **Detects** contradictions via semantic retrieval + LLM adjudication, with confidence scores.
5. **Finds** research gaps implied by future-work/limitation statements.
6. **Designs** concrete experiments to resolve top contradictions.
7. **Propagates** confidence across the graph (support raises, contradiction lowers).
8. **Answers** research questions with a plan → retrieve → reflect (≤3 iterations) → synthesize loop, producing a structured report with citations.
9. **Visualises** everything in six interlinked views.

### 2.3 Target users

| Persona | Need Axion addresses |
| :--- | :--- |
| **Research engineer / applied scientist** | Rapidly map a new field's agreements and disputes |
| **PhD student / academic** | Find gaps and unresolved disputes for a literature review |
| **R&D lead** | Track how consensus is shifting across a topic over years |
| **Founder / analyst** | Turn a research area into a structured, citable overview |
| **Lab / team** | Shared, persistent knowledge base instead of scattered notes |

### 2.4 Value proposition / differentiators

- **Claim-level, not document-level.** Everything is an atomic claim with provenance, not a PDF blob.
- **Contradiction-first.** The headline feature is surfacing and explaining conflicts, with a generated experiment to resolve them.
- **Explainable by construction.** Claims carry `evidence_span`, `section`, source paper, and a confidence score; contradictions carry an LLM explanation.
- **Temporal reasoning.** Consensus evolution and dispute timelines (not just a snapshot).
- **Self-hosted.** Your corpus and API keys stay on your machine; bring your own LLM keys.

### 2.5 Product surfaces (the UI)

The frontend is a single-page workspace with a nav rail (keyboard shortcuts 1–6)
and a `⌘K` command bar.

| # | View | ID | What the user sees / does |
| :-: | :--- | :--- | :--- |
| 1 | Research / Ask | `query` | Ask a research question; get a synthesized report, plan steps, reflection log, confidence, sources, and structured sections. Also shows **dashboard stats** and recent query history. |
| 2 | Knowledge Graph | `knowledge-graph` | Interactive force-directed canvas of Paper / Claim / Gap nodes with typed edges, hover detail, zoom, and a claim-count slider. |
| 3 | Contradictions | `contradictions` | List of detected contradictions with both claims, both papers, explanation, confidence %, a "min confidence" filter, and an on-demand **design experiment** action. |
| 4 | Research Gaps | `gaps` | Gaps (`semantic` or `llm_synthesized`) with related claims, plus targeted contradiction checks. |
| 5 | Timeline | `timeline` | Consensus evolution by year and a dispute timeline (resolved vs ongoing), for a chosen topic. |
| 6 | Graph Evolution | `evolution` | Confidence distribution and the "most changed" claims (base → current, delta, reason). |
| — | Ingestion sheet | — | Custom ingestion: choose a topic + paper count, watch real-time progress and logs. |
| — | Status bar / nav rail | — | Global stats (papers/claims/contradictions/gaps) and connection status. |

---

## 3. Capability matrix

Legend: ✅ works · 🟡 works with caveats · ❌ not implemented / unsupported.

### 3.1 Ingestion & extraction

| Capability | Status | Detail |
| :--- | :--: | :--- |
| arXiv search by topic | ✅ | `ingestion/arxiv_client.py` |
| PDF download + text extraction | ✅ | `ingestion/pdf_parser.py` (PyMuPDF) |
| Section-aware splitting | ✅ | chunk 800 / overlap 100 |
| LLM claim extraction | ✅ | `agents/reader.py`, ≤8 claims/paper |
| Provenance stamping | ✅ | claim → paper, section, evidence span |
| Structured claim fields | ✅ | subject / metric / direction / confidence |
| Automated periodic ingestion | 🟡 | APScheduler; off by default (`SCHEDULER_ENABLED`), single-worker only |
| Incremental / dedup-aware ingest | 🟡 | MERGE by `arxiv_id`; no cross-source dedup |
| PDFs other than arXiv | ❌ | arXiv-only |
| Non-English papers | ❌ | No language handling |

### 3.2 Graph & reasoning

| Capability | Status | Detail |
| :--- | :--: | :--- |
| Neo4j knowledge graph | ✅ | Paper/Claim/Gap nodes + typed edges |
| ChromaDB vector index | ✅ | 2,389 vectors in sync with Neo4j (last audit) |
| Contradiction detection | ✅ | similarity retrieval + LLM judge |
| Support detection | ✅ | `SUPPORTS` edges with explanation |
| Related-claim links | ✅ | `RELATED_TO` |
| Research gap discovery | 🟡 | from future-work/limitation text; confidence is not stored (returned `null`) |
| Experiment design | ✅ | stored on contradiction edges; on-demand + batch CLI |
| Confidence propagation | ✅ | `agents/confidence_updater.py` + endpoints + UI |
| Coordinator v2 (plan/reflect/synthesize) | ✅ | ≤3 reflection iterations |
| Temporal consensus evolution | ✅ | year-filtered retrieval + LLM narrative |
| Dispute timeline | ✅ | first-appeared / resolved / resolution year |
| Citation weighting | 🟡 | Semantic Scholar; 1.5 s/request sleep; needs network |
| Cross-paper only relationships | ✅ | the agent **refuses** to compare two claims from the same paper |
| Domain entity nodes (Benchmark/Dataset/Method) | ❌ | constraints declared but **no code populates them** |
| Community detection / graph summarisation | ❌ | referenced in docs only |

### 3.3 API & frontend

| Capability | Status | Detail |
| :--- | :--: | :--- |
| REST API | ✅ | 23 endpoints (see §5.6) |
| OpenAPI docs | ✅ | `/docs` (FastAPI default) |
| Web UI (6 views) | ✅ | Next.js; dark glass design system |
| Real-time query progress | 🟡 | job-level only (`queued` → `running` → `completed`); no per-stage progress |
| Streaming LLM responses | ❌ | single JSON response |
| Auth / accounts | 🟡 | shared `AXION_API_KEY` on write/compute + job routes; no accounts (see §9) |
| Persisted query history | 🟡 | `localStorage` only (per-browser) |
| Export (PDF/Markdown/report download) | ❌ | not implemented |
| Mobile layout | 🟡 | responsive-ish, not designed for mobile |

---

## 4. What the project CANNOT do (explicit limitations)

These are deliberate or missing capabilities as of this document. Treat this as
the honest "what not" list.

### 4.1 Product limitations

- **No user accounts, roles, or multi-tenancy.** Anyone who reaches the API can query it and trigger ingestion (if the shared secret is set).
- **No collaboration or sharing.** No workspaces, comments, or shared dashboards.
- **No export.** Reports and graphs cannot be downloaded as PDF/Markdown/CSV from the UI.
- **No mobile app / offline mode.**
- **No notifications or alerts** (e.g. "tell me when a new contradiction appears").
- **No domain coverage guarantees.** It has only been exercised on ML/LLM-flavoured topics (the default scheduler topics are all LLM-related).
- **No multilingual support.**
- **Query history is browser-local only** — it is not saved server-side, so it is lost across devices/browsers.

### 4.2 Correctness / data limitations

- **Same-paper claims are never compared.** By design `check_pair()` refuses two claims from the same `arxiv_id` (and, since the rebuild, only when *both* ids are non-empty). This is correct for real-world contradictions; the old same-paper-heavy labelled splits are superseded by `eval/Data/axion_pairs.csv` (see §8.2).
- **Low and now-measured contradiction precision.** A review of the 224 auto-detected CONTRADICTS edges found only **4 real ones** (11 SUPPORTS, 209 UNRELATED) — ~1.8% precision. On the rebuilt reference set the current LLM baseline reaches macro F1 0.48 and CONTRADICTS precision 0.15.
- **Contradiction/relationship detection is LLM-judged**, not verified. False positives and false negatives are expected; the reference set now puts a number on them.
- **Gap confidence is not stored**, so the UI shows no confidence for gaps.
- **No human-in-the-loop correction.** Users cannot accept/reject/edit a claim, contradiction, or experiment design, and nothing is fed back into the system.
- **Parse failures are now visible.** `check_pair()` accepts a `diagnostics` out-param; the eval harness distinguishes JSON parse failures from genuine `UNRELATED` verdicts and warns on them.
- **Confidence propagation is heuristic**, not calibrated to any ground truth.

### 4.3 Platform / engineering limitations

- **Job durability depends on Redis.** With `REDIS_URL` set (the compose default), job records live in Redis and are executed by the `worker` service, so jobs survive an API restart; RQ retries a job whose worker was killed. Without it the API falls back to an in-process thread pool and jobs are lost on restart.
- **State is mixed, not fully distributed.** The scheduler, in-memory metrics, and the ingestion running-flag remain process-local; ingestion is therefore single-process (the scheduler *enqueues* when a queue exists so the API and worker cannot ingest concurrently), and the worker should stay at 1 replica while `SCHEDULER_ENABLED=true`.
- **Queries are queued but not streamed.** `/api/query` returns `202` + a job id and the client polls; there is no per-stage progress, no partial output, and no cancellation endpoint.
- **No persistence for metrics/tracing.** `/api/metrics` is in-memory and resets on restart; no Prometheus, no tracing backend, no alerting.
- **Shared-key auth only, no per-user rate limiting.** Write/compute routes and job polling require `AXION_API_KEY` (fail-closed), but there are no accounts; rate limiting is a single global bucket (60/min by IP) with tighter limits on a few endpoints.
- **No schema migrations framework.** DB changes are ad-hoc scripts (`graph/migrate_*.py`, `graph/fix_*.py`).
- **Secrets in a plaintext `.env`.** No secret manager; the rotating policy is manual (and keys currently on disk need rotation).
- **Windows-oriented paths in a few legacy scripts** (fixed in the eval harness; some data-prep scripts still assume repo-root CWD).
- **No reproducible builds / lockfile hashes** for Python (fully pinned `==`, but not hashed) and no Python-version marker.

### 4.4 Deployment limitations (state before the current deployment work)

- Previously: **no Dockerfile, no CI, and only Neo4j in compose.** This has now been addressed (see §10) — Dockerfiles for API and frontend, full-stack compose, GitHub Actions CI.
- **No production reverse proxy / TLS / domain setup.**
- **No backups automation in containers** — the host-side backup utility shells out to Docker and is not wired into a schedule.

---

## 5. Technical architecture

### 5.1 High-level flow

```
             ┌──────────────┐        ┌──────────────────────────────┐
   arXiv ───▶│  ingestion   │──────▶ │ agents/reader.py             │
             │ (search+PDF) │        │  → structured claims         │
             └──────────────┘        └──────────────┬───────────────┘
                                                    │
                    ┌───────────────────────────────┼───────────────────────────┐
                    ▼                               ▼                           ▼
          ┌──────────────────┐            ┌──────────────────┐        ┌──────────────────┐
          │ Neo4j (graph)    │            │ ChromaDB (vectors│        │ data/papers/     │
          │ Paper/Claim/Gap  │            │  all-MiniLM-L6)  │        │ raw PDFs         │
          └────────┬─────────┘            └────────┬─────────┘        └──────────────────┘
                   │                               │
                   ▼                               ▼
        ┌──────────────────────────────────────────────────────────┐
        │ Reasoning agents                                         │
        │  contradiction · gap_finder · experiment_recommender ·   │
        │  confidence_updater · temporal · citation · coordinator_v2│
        └───────────────────────────┬──────────────────────────────┘
                                    ▼
                        ┌────────────────────────┐
                        │ FastAPI (api/main.py)  │  23 endpoints
                        └───────────┬────────────┘
                                    ▼
                        ┌────────────────────────┐
                        │ Next.js frontend (axion)│  6 views
                        └────────────────────────┘
```

### 5.2 Technology stack

| Layer | Technology | Notes / pins |
| :--- | :--- | :--- |
| Language (backend) | Python | 3.11 (`pytest` runs on 3.11.9) |
| Web framework | FastAPI + Uvicorn | `fastapi==0.136.3`, `uvicorn[standard]==0.48.0` |
| Validation | Pydantic | `pydantic==2.13.4` |
| Rate limiting | slowapi | `slowapi==0.1.9` |
| Graph DB | Neo4j | `neo4j==6.2.0` driver, server `5.18-community` (APOC) |
| Vector DB | ChromaDB | `chromadb==1.5.9` |
| Embeddings | sentence-transformers | `all-MiniLM-L6-v2`, `sentence-transformers==5.5.1` |
| PDF | PyMuPDF | `PyMuPDF==1.27.2.3` |
| LLM SDKs | Groq / Google GenAI / Anthropic | `groq==1.2.0`, `google-genai==2.6.0`, `anthropic==0.104.1` |
| Scheduling | APScheduler | `APScheduler==3.11.2` |
| (Legacy UI deps) | Streamlit / pyvis / plotly | still in `requirements.txt`; the Streamlit UI was retired |
| Frontend | Next.js / React / TypeScript | Next `16.2.6`, React `^19`, TS `5.7.3` |
| Styling | Tailwind CSS v4 + shadcn/ui | `tailwindcss ^4.2.0`, Radix primitives |
| Data fetching | SWR | `swr ^2.4.1` |
| Graphs | react-force-graph-2d | `^1.29.1` |
| Charts | Recharts | `2.15.0` |
| Package manager (web) | pnpm | lockfile committed |

### 5.3 The agent pipeline

| Agent | File | Responsibility | LLM? |
| :--- | :--- | :--- | :--: |
| Ingestion client | `ingestion/arxiv_client.py` | arXiv search + PDF download | ❌ |
| PDF parser | `ingestion/pdf_parser.py` | text + section extraction | ❌ |
| Reader | `agents/reader.py` | claim extraction + provenance | ✅ |
| Contradiction | `agents/contradiction.py` | `check_pair()` + batch detection | ✅ |
| Gap finder | `agents/gap_finder.py` | gaps from future-work/limitations | ✅ |
| Experiment recommender | `agents/experiment_recommender.py` | design resolving experiment | ✅ |
| Confidence updater | `agents/confidence_updater.py` | propagate support/contradiction into confidence | ❌ (heuristic) |
| Temporal | `agents/temporal.py` | year-filtered search, evolution, disputes | ✅ |
| Citation | `agents/citation.py` | Semantic Scholar citation counts | ❌ |
| Planner / Reflector / Synthesizer | `agents/planner.py`, `reflector.py`, `synthesizer.py` | components of the coordinator | ✅ |
| Coordinator v2 | `agents/coordinator_v2.py` | plan → retrieve → reflect (≤3) → synthesize | ✅ |

Embeddings live in `embeddings/store.py`; graph access in `graph/neo4j_*.py`.

### 5.4 Data model (Neo4j)

**Nodes**

| Label | Key | Notable properties |
| :--- | :--- | :--- |
| `Paper` | `arxiv_id` (unique) | title, authors, abstract, published, year |
| `Claim` | `claim_id` (unique) | text, section, confidence, base_confidence, paper_year, subject, metric, direction, evidence_span |
| `Gap` | `gap_id` (unique) | text, source (`semantic` \| `llm_synthesized`) |
| `Benchmark`, `Dataset`, `Method` | `name` (unique) | **declared in schema, never populated** |

**Relationships**

| Type | From → To | Properties |
| :--- | :--- | :--- |
| `EXTRACTED_FROM` | Claim → Paper | — |
| `CONTRADICTS` | Claim → Claim | explanation, confidence, (experiment design fields) |
| `SUPPORTS` | Claim → Claim | explanation, confidence |
| `RELATED_TO` | Gap → Claim | — |

**Indexes:** `claim_year`, `claim_section`, `paper_year`, `claim_confidence`, `claim_subject`, `claim_metric`, `claim_direction`.

**ChromaDB:** one collection of claim vectors, id `claim_<elementId>`, metadata includes `arxiv_id` and `paper_year` (int).

### 5.5 Storage layout

| Store | Location | Purpose |
| :--- | :--- | :--- |
| Neo4j | Docker volume `neo4j_data` (host port 7887 → 7687) | graph |
| ChromaDB | `data/db/chroma/` | claim embeddings |
| Papers | `data/papers/` | downloaded PDFs |
| Backups | `data/backups/` | graph backup utility output |
| Legacy SQLite | `data/db/axion.db` | retired; migration archived under `archive/` |
| HF model cache | `~/.cache/huggingface` (container volume `hf_cache`) | sentence-transformers model |

### 5.6 API reference (23 endpoints)

| Method | Path | Purpose | Auth | Rate limit |
| :--- | :--- | :--- | :--: | :--- |
| GET | `/healthz` | liveness (always 200) | — | global |
| GET | `/api/health` | readiness; 503 if Neo4j/Chroma down | — | global |
| GET | `/api/metrics` | in-memory metrics summary | — | global |
| GET | `/api/stats` | graph counts | — | global |
| GET | `/api/claims` | list claims (`limit`,`offset`) | — | global |
| GET | `/api/claims/{id}/provenance` | claim provenance chain | — | global |
| GET | `/api/contradictions` | all CONTRADICTS with details | — | global |
| GET | `/api/experiments/{contradiction_id}` | stored experiment design | — | global |
| POST | `/api/experiments/{contradiction_id}/design` | design experiment on demand | 🔑 | 5/min |
| GET | `/api/gaps` | gaps (`?source=`) | — | global |
| POST | `/api/query` | enqueue a research query (coordinator v2) → `202 {job_id}` | 🔑 | 10/min |
| GET | `/api/jobs` | recent jobs, newest first (`limit`) | 🔑 | global |
| GET | `/api/jobs/{job_id}` | job status/result (`queued`/`running`/`completed`/`failed`) | 🔑 | global |
| GET | `/api/temporal/evolution` | consensus evolution | — | global |
| GET | `/api/temporal/disputes` | dispute timeline | — | global |
| GET | `/api/confidence/distribution` | confidence histogram | — | global |
| GET | `/api/confidence/most-changed` | biggest confidence moves | — | global |
| POST | `/api/confidence/recalculate` | recompute confidence | 🔑 | 10/min |
| GET | `/api/ingestion/status` | last run + running flag (queue-aware) | — | global |
| POST | `/api/ingestion/trigger` | enqueue an ingestion cycle → `202` | 🔑 | 2/min |
| POST | `/api/ingestion/custom` | enqueue ingestion for a topic → `202` | 🔑 | 5/min |
| GET | `/api/ingestion/progress` | live progress + logs (Redis-mirrored) | — | global |
| GET | `/api/graph` | nodes/edges for the graph canvas | — | global |

🔑 = requires an `X-API-Key` header matching `AXION_API_KEY` (the legacy
`X-Trigger-Secret` header is still accepted). Read-only endpoints are public;
every endpoint that spends LLM tokens or mutates the graph requires the key, and
returns `503` when no key is configured (fail-closed).

Global rate limit: `60/minute` per client IP (slowapi).

### 5.7 Frontend architecture

- **Framework:** Next.js App Router; single route (`app/page.tsx`) switching views client-side.
- **Views:** `query-panel`, `knowledge-graph`, `contradiction-list`, `gap-list`, `timeline-view`, `graph-evolution`, plus `dashboard-stats`, `ingestion-status`, `experiment-card`, `nav-rail`, `status-bar`, `command-bar`.
- **API client:** `lib/api-client.ts` — direct fetches to `NEXT_PUBLIC_API_URL` for read-only endpoints; write/compute calls go through the server-side proxy `app/api/backend/[...path]/route.ts`, which attaches `X-API-Key` from `AXION_API_KEY` (never bundled into the client).
- **Types:** `types/axion.ts` mirrors API response models.
- **Design system:** dark "glass" theme, skeletons, empty/error states, `⌘K` command bar, keyboard nav.
- **Known dead weight:** none significant — the 47 unused `components/ui/*` primitives, orphaned `styles/globals.css`, duplicate hooks, and placeholder assets were removed; only the 10 used shadcn primitives remain.
- **Known rough edges:** `getHealth` is unused in `lib/api-client.ts`; `/api/claims/{id}/provenance` and `/api/metrics` are not surfaced in the UI; there are no view-level frontend tests and no committed screenshots.

### 5.8 LLM layer

- **Providers:** `groq` (primary), `gemini` (fallback), `claude` (available).
- **Chain:** `LLM_PROVIDER_CHAIN = ["groq", "gemini"]`.
- **Models:** `openai/gpt-oss-20b` (Groq), `gemini-3.8-flash` (Gemini, `GEMINI_MODEL`), `claude-sonnet-4-20250514` (Claude).
- **Resilience:** transient errors (5xx/timeouts) retry on a short schedule (`2, 5, 10` s); rate limits and hard failures fall through to the next provider; a provider that fails hard is **benched** for `LLM_PROVIDER_COOLDOWN_SECONDS` (300 s) instead of being retried on every call; empty-response guard, optional in-process cache (`LLM_CACHE_ENABLED`), per-call timing and metrics. Reasoning models (`gpt-oss-*`, `qwen3-*`) run with `reasoning_effort="low"`; Gemini 3.x runs with `GEMINI_THINKING_BUDGET=0` (it otherwise spends ~110–130 hidden thought tokens per call).
- **Rate-limit detection** covers all three providers' error shapes.

### 5.9 Configuration reference (environment variables)

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `GROQ_API_KEY` / `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` | — | LLM credentials |
| `LLM_CACHE_ENABLED` | `false` | in-process LLM response cache |
| `NEO4J_URI` | `bolt://localhost:7887` | graph connection |
| `NEO4J_USERNAME` / `NEO4J_PASSWORD` | `neo4j` / — | graph auth |
| `NEO4J_CONTAINER_NAME` | `axion_neo4j` | used by backup utility |
| `ALLOWED_ORIGINS` | `http://localhost:3000,http://localhost:5173` | CORS allow-list |
| `SCHEDULER_ENABLED` | `false` | run periodic ingestion in the API process |
| `SCHEDULER_INTERVAL_HOURS` | `6` | scheduler cadence |
| `SCHEDULER_PAPERS_PER_RUN` | `5` | papers per scheduler run |
| `AXION_API_KEY` | — (empty ⇒ write/compute endpoints disabled) | shared secret for query/experiment/confidence/ingestion **and job** endpoints (`X-API-Key`) |
| `TRIGGER_SECRET` | — (empty) | legacy alias accepted via `X-Trigger-Secret` |
| `REDIS_URL` | — (empty ⇒ in-process thread fallback) | Redis for the durable job queue + cross-process progress |
| `JOB_TTL_SECONDS` | `86400` | how long finished job records are kept |
| `JOB_TIMEOUT_SECONDS` | `1800` | per-job timeout handed to the queue |
| `CONTRADICTION_MAX_DISTANCE` | `0.35` | max cosine distance for a claim pair to reach the LLM judge |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Gemini model id |
| `GEMINI_THINKING_BUDGET` | `0` | Gemini thinking-token budget (`0` disables) |
| `LLM_PROVIDER_COOLDOWN_SECONDS` | `300` | how long a hard-failing provider is benched |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | frontend → API base URL (build-time) |
| `AXION_API_URL` | `http://localhost:8000` | backend address used by the Next.js server-side proxy |
| `LOG_LEVEL` | `INFO` | logging |

Non-env config (in `config.py`): embedding model, chunk size/overlap, `MAX_CLAIMS_PER_PAPER=8`, `GROQ_MODEL=openai/gpt-oss-20b`, `SCHEDULER_TOPICS` (5 LLM-related topics).

---

## 6. Data currently in the system

Verified live on 2026-10-17 against the containerized stack (`GET /api/stats`).

| Entity | Count |
| :--- | ---: |
| Papers | 48 |
| Claims | 2,389 |
| Vectors (ChromaDB) | 2,389 |
| Contradictions | 224 |
| Supports | 132 |
| Related-claim links | 93 |
| Gaps | 18 |
| Experiments designed | 36 |

⚠️ Data-integrity notes:
- The old labelled eval set's positives were all same-paper pairs; superseded by `eval/Data/axion_pairs.csv` (see §8.2).
- `eval/Data/Labeled_pairs.csv` is 0 bytes (Windows case collision); `axion_pairs.csv` is the reference set now.
- Ad-hoc migration/fix scripts in `graph/` (`migrate_*.py`, `fix_*.py`) have been run against this data; there is no migration log.

---

## 7. How to run

### 7.1 Local development

```bash
# 1. Backend
python -m venv venv
venv/Scripts/activate            # Windows;  source venv/bin/activate on Unix
pip install -r requirements-dev.txt
cp .env.example .env             # fill in LLM keys + NEO4J_PASSWORD + AXION_API_KEY
docker compose up -d neo4j       # graph only
python -m graph.neo4j_schema     # create constraints/indexes
uvicorn api.main:app --reload --port 8000

# 2. Frontend
cd axion
pnpm install
# axion/.env.local: NEXT_PUBLIC_API_URL=http://localhost:8000
#                   AXION_API_KEY=<same as root AXION_API_KEY>
pnpm dev                         # http://localhost:3000
```

CLI mode (batch jobs) is available via `main.py`:
`python main.py --mode {ingest,contradict,gaps,query,backup,schedule,citations,confidence,experiments}`.

### 7.2 Full stack with Docker (added in this pass)

```bash
cp .env.example .env     # fill in keys
docker compose up --build
# frontend  http://localhost:3000
# API docs  http://localhost:8000/docs
# Neo4j     bolt://localhost:7887  (browser http://localhost:7474)
```

Compose services: `neo4j` (healthchecked, loopback-bound), `api`
(CPU-only PyTorch, single worker, `/healthz` healthcheck, `./data` mounted),
`web` (Next.js standalone, ports 3000).

---

## 8. Testing & evaluation

### 8.1 Test suite

| Item | State |
| :--- | :--- |
| Offline suite | **111 passed, 6 deselected** |
| Integration tests | `tests/test_neo4j.py`, `tests/test_claims.py` — need live Neo4j, marked `integration`, deselected by default |
| CI | `.github/workflows/ci.yml` — backend offline tests + frontend build |
| `test_phase4.py` / `test_phase5.py` | script-style; collect **0** tests (silent no-ops) |
| Coverage | not measured; API/ingestion/coordinator happy paths thinly covered |
| Frontend lint | `pnpm lint` not configured (no ESLint) |
| Frontend types | enforced (build type-checks; `tsc --noEmit` clean) |

### 8.2 Evaluation harness (`eval/`)

- Single entry point: `python eval/run_eval.py --predictor majority|random|llm`.
- Metrics: accuracy, **macro F1** (headline), weighted F1, per-class P/R/F1/support, confusion matrix, latency stats, class composition, `warnings`, and `predictor_diagnostics`.
- Offline predictors (majority/random) make CI runnable without LLMs.

**Reference set (rebuilt 2026-10-17): `eval/Data/axion_pairs.csv`** — 286
cross-paper pairs (4 CONTRADICTS / 11 SUPPORTS / 271 UNRELATED), built by
`eval/Data/build_reference_set.py` from the only reviewed labels in the repo
(`contradicts_review_labeled.csv`, audited against the rubric in
`label_contradicts.py`) plus tagged negatives from `labeled_pairs_cleaned.csv`.

**Headline finding:** the review found only **4 of 224** auto-detected
CONTRADICTS are real (11 SUPPORTS, 209 UNRELATED) — production contradiction
precision is **~1.8%**. Recorded baselines on the reference set:

| predictor | accuracy | macro F1 | CONTRADICTS P / R |
| :--- | ---: | ---: | :--- |
| majority | 0.9476 | 0.3244 | 0.00 / 0.00 |
| random (seed 0) | 0.3706 | 0.2191 | — |
| llm (`openai/gpt-oss-20b`) | 0.8427 | 0.4822 | 0.154 / 0.500 |

The old splits remain unusable for the record: every SUPPORTS/CONTRADICTS label
was a same-paper pair, so the production-aligned eval was 100% UNRELATED and the
majority baseline scored accuracy 1.0 / macro F1 0.33. Targets still to meet:
macro F1 ≥ 0.55, CONTRADICTS precision/recall ≥ 0.60, p95 latency ≤ 4 s.

---

## 9. Security posture

| Area | State |
| :--- | :--- |
| Authentication | ✅ shared `AXION_API_KEY` on all write/compute endpoints (fail-closed); ❌ no per-user accounts |
| Authorization / roles | ❌ none (single shared secret) |
| Transport security | ❌ no TLS/reverse proxy |
| Secret storage | ⚠️ plaintext `.env` (gitignored, but keys on disk need rotation) |
| Secret leakage to client | ✅ fixed: the key is attached by the Next.js server-side proxy; verified absent from the served JS bundles |
| Neo4j exposure | ✅ bound to `127.0.0.1` only (this pass) |
| APOC | ⚠️ `apoc.*` unrestricted in Neo4j |
| CORS | allow-list from `ALLOWED_ORIGINS`; `allow_credentials=True` |
| Rate limiting | global 60/min per IP + a few tighter limits; no per-user limits |
| Error handling | ✅ generic 500 body; details logged, not returned (this pass) |
| Dependency hygiene | ✅ fully pinned `==` (no hashes) |
| License | ❌ none specified |

**Bottom line:** no longer trivially abusable (compute/graph mutations require the
key), but still not safe to expose to untrusted users as is. Minimum before
multi-user use: a real identity layer, TLS, secret-manager rotation, and per-user
rate limits.

Verified 2026-10-17 against the running stack: anonymous and wrong-key calls to
`/api/query`, `/api/experiments/{id}/design` and `/api/confidence/recalculate`
return `401`; the frontend proxy reaches the API with a valid key; and neither
`AXION_API_KEY` nor the legacy `TRIGGER_SECRET` appears in any served JS chunk.

---

## 10. Deployment & operations

### 10.1 What was added in this pass

- `Dockerfile` (API): `python:3.11-slim`, **CPU-only PyTorch** (avoids ~2.5 GB CUDA), pinned `requirements.txt`, `/healthz` healthcheck, single-worker Uvicorn.
- `axion/Dockerfile`: multi-stage Node 20 + pnpm, Next.js **standalone** output, non-root user, healthcheck.
- `docker-compose.yml`: `neo4j` + `api` + `web`, health-gated startup, `./data` bind mount, `hf_cache` model volume, `.env` interpolation, compose project name `axion`.
- `.dockerignore` (root + frontend) to keep contexts small and secrets out of images.
- `GET /healthz` liveness endpoint (distinct from readiness `/api/health`).
- `requirements-dev.txt` (pytest, pytest-cov, httpx, numpy, pandas, scikit-learn).

Validated: `docker compose config` parses; frontend standalone bundle builds.
**Not validated:** image builds/run (Docker daemon was unavailable on this machine).

### 10.2 Operational gaps (still open)

- No reverse proxy / TLS / domain setup.
- Durable queue ✅ (RQ + Redis + `worker` service, verified live); the scheduler, metrics, and progress-flag remain process-local.
- No persistent metrics/tracing/alerting.
- Neo4j backup utility is host-only (shells out to Docker), not scheduled in compose.
- No migration framework; ad-hoc scripts only.
- No resource limits / autoscaling.

---

## 11. Known bugs, risks & technical debt

Consolidated (details and checkboxes in `progress.md`):

**Fixed in this work session**
- `get_graph_stats` returned `{}` when gaps/contradictions were 0 → all-zero `/api/stats`.
- Temporal endpoints returned fabricated data (wrong schema mapping).
- Ingestion trigger secret **failed open** when unset → now fail-closed.
- Global exception handler leaked raw `str(exc)` → now generic + logged.
- Hardcoded placeholders (gap confidence `0.8`, paper year `2024`, `"Unknown"` section / empty arxiv id).
- API crashed on startup if Neo4j/Chroma down → now boots degraded.
- Docker port/container-name drift (host port and container name disagreed with `docker-compose.yml`).
- Offline `pytest` uncollectable (broken `test_claims.py`, live-LLM test leak, no markers).
- 4 frontend type errors; `ignoreBuildErrors` removed.
- Eval harness rewritten; `eval/data` case bugs fixed.
- Eval dataset rebuilt (`eval/Data/axion_pairs.csv`); parse failures now instrumented.
- LLM router health: the configured Groq model was decommissioned and non-rate-limit errors aborted the whole fallback chain — now `openai/gpt-oss-20b` / `gemini-3.8-flash` with full fallback, transient retry, an empty-response guard, and a 300 s provider cooldown.
- Contradiction retrieval gate was inert (`0.95` passed 100 % of pairs) → `CONTRADICTION_MAX_DISTANCE=0.35` (passes 42.6 %), measured by `eval/measure_gate.py`.
- Job queue shipped (RQ + Redis + worker); `/api/query` and ingestion triggers return `202` + job id, `GET /api/jobs…` is key-guarded.
- Redis client `decode_responses=True` crashed every RQ worker on startup (`'str' object has no attribute 'decode'`) → bytes mode + regression tests.

**Open**
- No per-user accounts (single shared `AXION_API_KEY`); no TLS.
- Post-change LLM eval **blocked on provider quota** (Groq 200k tokens/day, Gemini 20 requests/day); CONTRADICTS has only 4 examples — expand the reviewed set. Macro F1 0.48 (prefix baseline) is the current honest number.
- Scheduler + metrics remain process-local; the worker must stay at 1 replica while the scheduler is enabled.
- No job cancellation or per-stage progress.
- Ingestion state `/api/ingestion/status` correctness now reported, but in-memory.
- Gaps have no stored confidence.
- Untracked docs + `eval/` now committed; `eval/Data/Labeled_pairs.csv` remains 0 bytes (historical).
- No Python-version marker; no hash-pinned deps.

---

## 12. Shipment readiness

| Target | Estimate | What's left |
| :--- | :--- | :--- |
| **Founder/demo** | **~92%** | Polish; the core loop works and looks finished |
| **Self-hosted MVP** | **~88–90%** | Auth ✅ + deployment ✅ + durable queue ✅; remaining: observability, ops docs, a defensible contradiction-quality measurement |
| **Multi-tenant SaaS** | **~50%** | Identity/tenancy, observability, valid eval, billing — 2–3+ months |

**Verdict:** everything needed for a compelling demo exists, the stack is no
longer trivially abusable (write/compute endpoints require a server-held key),
and long work is durable and isolated from the request path. Shipping a *product*
is now blocked mainly on **observability/ops** and a **larger, valid evaluation
with provider quota** — not on features.

---

## 13. Roadmap to production (ordered)

1. **P0 correctness/security** — ✅ done (stats, temporal, fail-closed secret, error leak, placeholders, degraded boot).
2. **Offline-green tests + CI** — ✅ done (229 tests, GitHub Actions, type-checked build).
3. **Deployment** — ✅ done (Dockerfiles, full-stack compose, healthchecks).
4. **Valid evaluation** — ✅ reference set rebuilt + baselines recorded (`axion_pairs.csv`, macro F1 0.48) and the retrieval gate measured; ⏳ the post-change LLM run is blocked on provider quota and CONTRADICTS needs more reviewed positives.
5. **Auth + multi-user** — shared-key auth on compute endpoints ✅ done; real accounts, per-user rate limits still open.
6. **Durable task queue** — ✅ done (RQ + Redis + `worker` service, cross-process verified); metrics/scheduler state still process-local.
7. **Observability** — persistent metrics, tracing, alerting, structured logs.
8. **Docs/branding** — ✅ unified on **Axion**, stats reconciled, LICENSE added, side docs banner-ed; folder rename outstanding.
9. **Frontend cleanup** — ✅ dead code deleted, health indicators real; provenance/metrics views and frontend tests still open.

---

## 14. Naming & branding

- **Canonical name:** **Axion** (decided and applied 2026-10-16).
- Rename pass **complete** in code, config, and docs: `config.py`, `api/main.py`, `main.py`, `embeddings/store.py`, `agents/synthesizer.py`, `archive/coordinator_v1.py`, `graph/migrate_to_neo4j.py`, `requirements.txt`, `axion/types/axion.ts`, `.env.example`, `docker-compose.yml` (container `axion_neo4j`), `tests/test_axion.py`, README, and all side docs. The legacy SQLite file was renamed to `data/db/axion.db`.
- The **GitHub repo** was renamed to `Axion` (2026-10-17) and the `origin` remote re-pointed.
- Remaining out-of-band artifact: the **on-disk folder** (`schimesh`).

---

## 15. Repository map (selected)

```
schimesh/
├─ api/                 main.py (23 endpoints), models.py
├─ jobs/                backend, store, tasks, worker, redis_conn (durable queue)
├─ agents/              reader, contradiction, gap_finder, experiment_recommender,
│                       confidence_updater, temporal, citation, planner, reflector,
│                       synthesizer, coordinator_v2
├─ ingestion/           arxiv_client, pdf_parser, scheduler, progress
├─ embeddings/          store.py (ChromaDB)
├─ graph/               neo4j_client, neo4j_queries, neo4j_schema, backup,
│                       migrate_*.py, fix_*.py (ad-hoc)
├─ utils/               metrics, logger, llm_cache, llm_parser, ingestion_report
├─ planner/             (planner-related package)
├─ axion/               Next.js frontend (app/, components/axion/, lib/, types/)
├─ eval/                run_eval.py, metrics.py, dataset.py, predictors.py, Data/, results/, README.md
├─ tests/               229 offline tests + integration tests
├─ .github/workflows/   ci.yml
├─ Dockerfile           backend image
├─ axion/Dockerfile     frontend image
├─ docker-compose.yml   full stack
├─ requirements.txt     pinned runtime deps
├─ requirements-dev.txt runtime + test/eval deps
├─ config.py            all configuration
├─ main.py              CLI (batch modes)
├─ progress.md          actionable tracker (untracked)
└─ PROJECT_INFO.md      this document
```

---

## 16. Glossary

| Term | Meaning |
| :--- | :--- |
| **Claim** | An atomic, structured assertion extracted from a paper, with provenance. |
| **Contradiction** | Two claims that assert incompatible things (`CONTRADICTS` edge) with an explanation + confidence. |
| **Support** | Two claims that corroborate each other (`SUPPORTS`). |
| **Gap** | An unexplored area / unanswered question derived from future-work text or missing links. |
| **Coordinator v2** | The multi-step query agent: plan → retrieve → reflect → synthesize. |
| **Provenance** | The chain claim → paper → section → evidence span. |
| **Confidence** | A computed score per claim; propagated from support/contradiction signals. |
| **Same-paper pair** | Two claims from the same `arxiv_id` — never compared by the agent. |
| **Macro F1** | Unweighted mean F1 across classes; the eval's headline metric. |

---

*Maintenance: keep this file in sync with `progress.md` (actions) and
`eval/README.md` (evaluation). When a limitation in §4 is resolved, move the
item to the "fixed" list in §11 and update §12.*
