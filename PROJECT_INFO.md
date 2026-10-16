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
| **API endpoints** | 21 (20 functional + `/healthz` liveness) |
| **UI surfaces** | 6 views + dashboard stats + ingestion sheet |
| **Tests** | 111 passing offline, 6 integration deselected |
| **Data (last audit)** | 48 papers · 2,389 claims · 224 contradictions · 132 supports · 93 related · 30 gaps · 12 experiments |
| **Demo readiness** | ~85% |
| **Product readiness** | ~40% (see §12) |
| **Licence** | Not specified in repo (⚠️ missing) |

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
| REST API | ✅ | 21 endpoints (see §5.6) |
| OpenAPI docs | ✅ | `/docs` (FastAPI default) |
| Web UI (6 views) | ✅ | Next.js; dark glass design system |
| Real-time query progress | ❌ | fake animation during query load |
| Streaming LLM responses | ❌ | single JSON response |
| Auth / accounts | ❌ | none (see §9) |
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

- **Same-paper claims are never compared.** By design `check_pair()` refuses two claims from the same `arxiv_id`. This is correct for real-world contradictions, but it means the current *labelled eval set is unusable* (see §8.2).
- **No valid evaluation.** The labelled dataset's positives are all same-paper pairs, so the production-aligned eval is 100% `UNRELATED`. There is currently **no trustworthy accuracy/F1 number** for the core classifier.
- **Contradiction/relationship detection is LLM-judged**, not verified. False positives and false negatives are expected and unmeasured.
- **Gap confidence is not stored**, so the UI shows no confidence for gaps.
- **No human-in-the-loop correction.** Users cannot accept/reject/edit a claim, contradiction, or experiment design, and nothing is fed back into the system.
- **Parse failures are invisible.** `check_pair()` returns `None` for UNRELATED, same-paper, *and* JSON parse failure alike — a silent failure looks like a negative verdict.
- **Confidence propagation is heuristic**, not calibrated to any ground truth.

### 4.3 Platform / engineering limitations

- **Single API worker only.** The ingestion scheduler, metrics, and ingestion-progress tracker are in-memory and process-local. Running multiple workers duplicates ingestion and desynchronises state.
- **No durable task queue.** Ingestion runs in a background thread/in-process; long jobs are lost on restart. `README` plans Celery/RQ; it is not built.
- **Blocking LLM calls inside requests.** `/api/query` runs the entire (multi-iteration) LLM loop synchronously; LLM back-off can `sleep` up to 300 s. A slow query ties up a worker.
- **No persistence for metrics/tracing.** `/api/metrics` is in-memory and resets on restart; no Prometheus, no tracing backend, no alerting.
- **No auth, no per-user rate limiting.** Rate limiting is a single global bucket (60/min by IP), with tighter limits on a few endpoints.
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
                        │ FastAPI (api/main.py)  │  21 endpoints
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

### 5.6 API reference (21 endpoints)

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
| POST | `/api/experiments/{contradiction_id}/design` | design experiment on demand | — | 5/min |
| GET | `/api/gaps` | gaps (`?source=`) | — | global |
| POST | `/api/query` | full research query (coordinator v2) | — | global |
| GET | `/api/temporal/evolution` | consensus evolution | — | global |
| GET | `/api/temporal/disputes` | dispute timeline | — | global |
| GET | `/api/confidence/distribution` | confidence histogram | — | global |
| GET | `/api/confidence/most-changed` | biggest confidence moves | — | global |
| POST | `/api/confidence/recalculate` | recompute confidence | — | 10/min |
| GET | `/api/ingestion/status` | last run + running flag | — | global |
| POST | `/api/ingestion/trigger` | run ingestion cycle | 🔑 | 2/min |
| POST | `/api/ingestion/custom` | run ingestion for a topic | 🔑 | 5/min |
| GET | `/api/ingestion/progress` | live progress + logs | — | global |
| GET | `/api/graph` | nodes/edges for the graph canvas | — | global |

🔑 = requires `X-Trigger-Secret` header matching `TRIGGER_SECRET`. **All other
endpoints are unauthenticated.**

Global rate limit: `60/minute` per client IP (slowapi).

### 5.7 Frontend architecture

- **Framework:** Next.js App Router; single route (`app/page.tsx`) switching views client-side.
- **Views:** `query-panel`, `knowledge-graph`, `contradiction-list`, `gap-list`, `timeline-view`, `graph-evolution`, plus `dashboard-stats`, `ingestion-status`, `experiment-card`, `nav-rail`, `status-bar`, `command-bar`.
- **API client:** `lib/api-client.ts` — one fetch helper reading `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).
- **Types:** `types/axion.ts` mirrors API response models.
- **Design system:** dark "glass" theme, skeletons, empty/error states, `⌘K` command bar, keyboard nav.
- **Known dead weight:** ~51 unused `components/ui/*` primitives, orphaned `styles/globals.css`, duplicate hooks (`use-mobile`, `use-toast`), placeholder assets.
- **Known rough edges:** hardcoded "System Online" dot, "Neo4j Connected" inferred not checked, fake pipeline animation, an async call in a render body (`experiment-card.tsx`), unused `getClaims`/`getHealth`.

### 5.8 LLM layer

- **Providers:** `groq` (primary), `gemini` (fallback), `claude` (available).
- **Chain:** `LLM_PROVIDER_CHAIN = ["groq", "gemini"]`.
- **Models:** `llama-3.1-8b-instant` (Groq), `gemini-2.0-flash` (Gemini), `claude-sonnet-4-20250514` (Claude).
- **Resilience:** exponential back-off with jitter (`5, 15, 45, 120, 300` s), provider fallback, optional in-process cache (`LLM_CACHE_ENABLED`), per-call timing and metrics.
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
| `TRIGGER_SECRET` | — (empty ⇒ triggers disabled) | shared secret for ingestion endpoints |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | frontend → API base URL (build-time) |
| `NEXT_PUBLIC_TRIGGER_SECRET` | — | frontend's copy of the trigger secret (build-time, **public**) |
| `LOG_LEVEL` | `INFO` | logging |

Non-env config (in `config.py`): embedding model, chunk size/overlap, `MAX_CLAIMS_PER_PAPER=8`, `CONTRADICTION_THRESHOLD=0.95`, `SCHEDULER_TOPICS` (5 LLM-related topics).

---

## 6. Data currently in the system

From the last audit (2026-10-16). **Unverifiable right now** because no Neo4j
instance was running; numbers come from the local Neo4j volume and API.

| Entity | Count |
| :--- | ---: |
| Papers | 48 |
| Claims | 2,389 |
| Vectors (ChromaDB) | 2,389 |
| Contradictions | 224 |
| Supports | 132 |
| Related-claim links | 93 |
| Gaps | 30 |
| Experiments designed | 12 |

⚠️ Data-integrity notes:
- The labelled eval set's positives are all same-paper pairs (see §8.2).
- `eval/Data/Labeled_pairs.csv` is 0 bytes; the eval source dataset is missing.
- Ad-hoc migration/fix scripts in `graph/` (`migrate_*.py`, `fix_*.py`) have been run against this data; there is no migration log.

---

## 7. How to run

### 7.1 Local development

```bash
# 1. Backend
python -m venv venv
venv/Scripts/activate            # Windows;  source venv/bin/activate on Unix
pip install -r requirements-dev.txt
cp .env.example .env             # fill in LLM keys + NEO4J_PASSWORD + TRIGGER_SECRET
docker compose up -d neo4j       # graph only
python -m graph.neo4j_schema     # create constraints/indexes
uvicorn api.main:app --reload --port 8000

# 2. Frontend
cd axion
pnpm install
# axion/.env.local: NEXT_PUBLIC_API_URL=http://localhost:8000
#                   NEXT_PUBLIC_TRIGGER_SECRET=<same as root TRIGGER_SECRET>
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
- Metrics: accuracy, **macro F1** (headline), weighted F1, per-class P/R/F1/support, confusion matrix, latency stats, class composition, and explicit `warnings`.
- Offline predictors (majority/random) make CI runnable without LLMs.

**The critical finding — the dataset cannot measure production behaviour:**

| split | CONTRADICTS | SUPPORTS | UNRELATED | cross-paper rows |
| :--- | ---: | ---: | ---: | ---: |
| train | 3 | 83 | 124 | 48 (all UNRELATED) |
| val | 1 | 17 | 27 | 10 (all UNRELATED) |
| test | 1 | 18 | 26 | 10 (all UNRELATED) |

**Every SUPPORTS and CONTRADICTS label is a same-paper pair**, which the
production agent refuses to score. Production-aligned eval is therefore 100%
UNRELATED, and the majority baseline scores **accuracy 1.0 / macro F1 0.33**. A
valid evaluation **requires rebuilding the dataset with cross-paper pairs that
carry real positive labels.** Targets (proposed, unverified): macro F1 ≥ 0.55,
CONTRADICTS recall ≥ 0.60, p95 latency ≤ 4 s.

---

## 9. Security posture

| Area | State |
| :--- | :--- |
| Authentication | ❌ none, except shared-secret on 2 ingestion endpoints |
| Authorization / roles | ❌ none |
| Transport security | ❌ no TLS/reverse proxy |
| Secret storage | ⚠️ plaintext `.env` (gitignored, but keys on disk need rotation) |
| Secret leakage to client | ⚠️ `NEXT_PUBLIC_TRIGGER_SECRET` is public by design |
| Neo4j exposure | ✅ bound to `127.0.0.1` only (this pass) |
| APOC | ⚠️ `apoc.*` unrestricted in Neo4j |
| CORS | allow-list from `ALLOWED_ORIGINS`; `allow_credentials=True` |
| Rate limiting | global 60/min per IP + a few tighter limits; no per-user limits |
| Error handling | ✅ generic 500 body; details logged, not returned (this pass) |
| Dependency hygiene | ✅ fully pinned `==` (no hashes) |
| License | ❌ none specified |

**Bottom line:** not safe to expose to untrusted users or the public internet as
is. Minimum before multi-user use: real auth on write/compute endpoints, TLS,
secret-manager rotation, and per-user rate limits.

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
- No durable queue; ingestion lost on restart; multi-worker unsafe.
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

**Open**
- No auth; public `NEXT_PUBLIC_TRIGGER_SECRET`.
- No valid evaluation (dataset unusable, see §8.2).
- Scheduler + progress/metrics not multi-process safe; no task queue.
- Blocking LLM work inside `/api/query`.
- Ingestion state `/api/ingestion/status` correctness now reported, but in-memory.
- Gaps have no stored confidence.
- `check_pair` hides parse failures as UNRELATED.
- Dead Streamlit/pyvis/plotly deps; ~51 unused UI components.
- Docs/branding contradictions (three names, conflicting stats, references to deleted files).
- Untracked docs + `eval/` not in git; `Labeled_pairs.csv` 0 bytes.
- No license; no Python-version marker; no hash-pinned deps.

---

## 12. Shipment readiness

| Target | Estimate | What's left |
| :--- | :--- | :--- |
| **Founder/demo** | **~85%** | Polish; the core loop works and looks finished |
| **Self-hosted MVP** | **~70–75%** | Hardening: auth, queue, ops, docs, CI — mostly non-feature work |
| **Multi-tenant SaaS** | **~40%** | Auth/tenancy, durable jobs, observability, valid eval, billing — 2–3+ months |

**Verdict:** everything needed for a compelling demo exists. Shipping a *product*
is blocked mainly on **security (auth), a valid evaluation, and operational
durability**, not on features.

---

## 13. Roadmap to production (ordered)

1. **P0 correctness/security** — ✅ done this session (stats, temporal, fail-closed secret, error leak, placeholders, degraded boot).
2. **Offline-green tests + CI** — ✅ done (111 tests, GitHub Actions, type-checked build).
3. **Deployment** — ✅ done this session (Dockerfiles, full-stack compose, healthchecks).
4. **Valid evaluation** — ⛔ blocked: rebuild a cross-paper labelled dataset; then re-run the LLM baseline and set thresholds.
5. **Auth + multi-user** — real accounts, per-user rate limits, protect compute endpoints.
6. **Durable task queue** — Celery/RQ for ingestion + long queries; make state cross-process.
7. **Observability** — persistent metrics, tracing, alerting, structured logs.
8. **Docs/branding** — unify on **Axion**, reconcile stats, retire stale docs, add LICENSE.
9. **Frontend cleanup** — delete dead code, wire or remove unused API calls, real health indicators.

---

## 14. Naming & branding

- **Canonical name:** **Axion** (decided and applied 2026-10-16).
- Rename pass **complete** in code, config, and docs: `config.py`, `api/main.py`, `main.py`, `embeddings/store.py`, `agents/synthesizer.py`, `archive/coordinator_v1.py`, `graph/migrate_to_neo4j.py`, `requirements.txt`, `axion/types/axion.ts`, `.env.example`, `docker-compose.yml` (container `axion_neo4j`), `tests/test_axion.py`, README, and all side docs. The legacy SQLite file was renamed to `data/db/axion.db`.
- Remaining out-of-band artifact: the **on-disk folder** (`schimesh`) and the **GitHub repo** (`AetherGraph`) keep their old names; rename those to match, then the README clone URL (`.../Axion`) resolves.

---

## 15. Repository map (selected)

```
schimesh/
├─ api/                 main.py (21 endpoints), models.py
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
├─ tests/               111 offline tests + integration tests
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
