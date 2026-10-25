# Axion — Full Project Brief

> **Last verified against the repository:** 2026-10-24
> **Branch / HEAD:** `main` @ `0da2919` (`test: isolate job auth check from local env`)
> **Working tree at verification:** clean before this brief was added
> **Offline test result:** `229 passed, 12 deselected` in ~9.5 s
> **Status:** self-hosted research prototype; demo-ready with caveats, not production-ready
> **Naming:** the product is **Axion**; the repository folder is still `schimesh`, and older docs use SciMesh/AetherGraph.

This document is the single, self-contained context file for Axion. It describes
what the system is, why it exists, how it is built, what is actually working,
what is only partially working, and what must not be claimed about it. It is
written for a new engineer, reviewer, collaborator, or evaluator who needs to
understand the project without reading every other document first.

Where the older docs disagree with the code, this brief follows the code and
calls out the discrepancy. The main examples are listed in
[Documentation drift](#154-documentation-drift-worth-knowing).

---

## Table of contents

1. [Executive summary](#1-executive-summary)
2. [Problem and product thesis](#2-problem-and-product-thesis)
3. [Product overview](#3-product-overview)
4. [Current state](#4-current-state)
5. [Architecture](#5-architecture)
6. [End-to-end pipelines](#6-end-to-end-pipelines)
7. [Code and agent inventory](#7-code-and-agent-inventory)
8. [Data model and storage](#8-data-model-and-storage)
9. [API, authentication, and jobs](#9-api-authentication-and-jobs)
10. [Frontend and design system](#10-frontend-and-design-system)
11. [Configuration](#11-configuration)
12. [Running Axion](#12-running-axion)
13. [Testing, CI, and evaluation](#13-testing-ci-and-evaluation)
14. [Security posture](#14-security-posture)
15. [Known limitations and documentation drift](#15-known-limitations-and-documentation-drift)
16. [Roadmap](#16-roadmap)
17. [Repository map](#17-repository-map)
18. [Onboarding reading order](#18-onboarding-reading-order)
19. [Glossary](#19-glossary)
20. [Bottom line](#20-bottom-line)

---

## 1. Executive summary

**Axion is a claim-level scientific knowledge graph with a contradiction-first
workflow.** It ingests research papers from arXiv, extracts atomic claims with
provenance, embeds them, stores them in Neo4j and ChromaDB, and asks an LLM to
classify cross-paper claim pairs as `CONTRADICTS`, `SUPPORTS`, or `UNRELATED`.
On top of that graph it derives research gaps, proposes minimal experiments that
could resolve contradictions, tracks consensus over time, and recomputes
claim confidence from supporting and conflicting evidence.

The distinguishing idea is not "chat with papers." It is:

1. **Claims are the unit of knowledge**, not documents or chunks.
2. **Every claim keeps provenance**: source paper, section, and an evidence span.
3. **Conflicts are first-class objects** that can be inspected, explained, and
   turned into an experiment proposal.
4. **Answers are graph-derived and cited**, through a multi-step
   planner → retriever → reflector → synthesizer pipeline.

### What is working

- End-to-end arXiv ingestion: search, PDF download, section parsing, chunking,
  claim extraction, provenance storage, and embedding.
- A Neo4j graph with `Paper`, `Claim`, and `Gap` nodes; `EXTRACTED_FROM`,
  `CONTRADICTS`, `SUPPORTS`, and `RELATED_TO` edges; idempotent schema setup.
- A retrieval gate plus LLM judge plus deterministic decomposition guard for
  relationship classification.
- A six-view Next.js workspace with a distinctive "Cobalt Grid" design.
- A FastAPI service with 22 `/api` routes plus `/healthz`, shared-key auth on
  write/compute routes, and a server-side Next.js proxy that keeps the key out
  of the browser.
- Durable background jobs through Redis + RQ, with an in-process fallback.
- Docker Compose stack: Neo4j, Redis, API, worker, and web.
- A pre-registered four-variant judge ablation with cached, reproducible results.
- 229 offline tests and GitHub Actions CI for backend tests and frontend
  lint/build.

### What is not proven

- **Contradiction quality is not established.** The live graph contains 224
  auto-detected `CONTRADICTS` edges, but the evaluation has only **4**
  human-confirmed positives. An audit of 224 old production detections found 4
  true positives and 220 false positives. The four-variant pilot shows the 0.35 gate suppresses most audited
  false positives, but it also drops true positives; the decomposition guard
  made no measurable difference on this dataset.
- **Gap discovery is only partially wired.** The cluster-gap path runs; the
  future-work extractor exists but is not called by `run_gap_finding()`.
- **The deployment is single-tenant and prototype-grade**: one shared API key,
  no user accounts, no TLS, in-memory metrics, no migration framework, and no
  human-in-the-loop correction workflow.
- **Demo readiness is conditional.** The last operational check found Docker
  stopped, and live LLM calls depend on provider quota.

**One-sentence framing:** Axion is a working, tested, self-hosted research
prototype that demonstrates a claim-level contradiction workflow end to end; it
is not yet a validated scientific discovery system or a multi-tenant product.

---

## 2. Problem and product thesis

### 2.1 The problem

Scientific literature is too large and too fragmented to track manually. A
researcher asking "what is known about X?" faces:

- thousands of papers with incompatible terminology;
- findings buried in sections that are hard to search;
- claims that depend on specific datasets, metrics, and conditions;
- direct conflicts that are rarely stated explicitly;
- "future work" and limitation sections that quietly define the frontier;
- consensus that shifts over years, with no easy way to see how.

Document-level retrieval and generic chat interfaces help find passages, but
they lose the relationships between findings. Two papers can both be retrieved
for the same query while making opposite claims, and a chunk-based system has no
native representation of that conflict.

### 2.2 The thesis

If claims are extracted as structured, provenance-bearing objects, then a graph
of claims can support reasoning that document search cannot:

- **Conflict detection:** compare claims across papers instead of comparing
  documents.
- **Evidence tracing:** every assertion points back to a section and span.
- **Gap discovery:** find questions that clusters of claims circle but do not
  answer.
- **Experiment design:** turn a disagreement into a testable procedure.
- **Temporal analysis:** observe how claim positions and confidence change by
  publication year.
- **Confidence propagation:** let supporting and contradicting edges update a
  claim's standing.

The product bet is that **contradiction is the highest-value entry point** into
a literature: it is concrete, actionable, and naturally leads to an experiment.

### 2.3 Design principles visible in the code

- **Provenance over fluency.** Claims carry section, evidence span, and paper
  metadata; the answer layer is expected to cite arXiv IDs.
- **Deterministic guards around LLM output.** The contradiction judge must
  justify a conflict with three explicit booleans, or the verdict is demoted.
- **Graph as source of truth.** ChromaDB is a retrieval index; Neo4j holds the
  canonical entities and relationships.
- **Fail closed on writes.** If the shared API key is not configured, mutating
  and compute endpoints return 503 rather than running unprotected.
- **Heavy work belongs in jobs.** Ingestion and multi-step research queries are
  queued, return `202`, and are polled.
- **No key in the browser.** The Next.js server proxy attaches credentials.

---

## 3. Product overview

### 3.1 What Axion does

Axion provides six user-facing views and a set of supporting APIs:

| Surface | What the user can do |
| :--- | :--- |
| **Research** | Ask a natural-language research question; receive a multi-step, cited report; inspect the plan and reflection trace. |
| **Knowledge Graph** | Explore papers, claims, and relationships on an interactive canvas. |
| **Contradictions** | Browse detected conflicts, read the explanation, inspect both claims and their papers, and request an experiment design. |
| **Research Gaps** | Browse open questions derived from claim clusters (and, in principle, future-work text). |
| **Timeline** | See consensus positions and disputes by publication year for a topic. |
| **Graph Evolution** | Inspect confidence distribution and the claims whose confidence changed most. |

Supporting capabilities:

- arXiv topic search and batch ingestion;
- PDF parsing and section-aware chunking;
- structured claim extraction with evidence spans;
- 384-dimensional local embeddings (`all-MiniLM-L6-v2`);
- semantic candidate retrieval and LLM adjudication;
- contradiction explanations and demotion guard;
- experiment recommendations stored on contradiction edges;
- heuristic confidence propagation;
- citation counts from Semantic Scholar;
- background job queue and worker;
- Prometheus-replaceable in-memory metrics summary (JSON, no external backend);
- authenticated ingestion triggers and job polling.

### 3.2 What Axion is not

- **Not a chatbot over PDFs.** The primary object is a claim graph, not a
  document index.
- **Not a systematic-review tool.** It does not implement PRISMA-style screening,
  dual extraction, or meta-analysis.
- **Not a validated fact-checker.** LLM judgments can be wrong; the guard is
  designed to reduce one failure mode but does not solve correctness.
- **Not multi-tenant.** No accounts, roles, per-user quotas, or audit trail.
- **Not a production SaaS.** No TLS termination, horizontal API scaling, managed
  migrations, or HA datastores in the repository.
- **Not domain-general.** Ingestion is arXiv-centric and optimized for
  English-language AI/ML papers.

### 3.3 Target users

Primary:

- AI/ML researchers and PhD students tracking a fast-moving literature;
- research engineers and applied scientists who need to map evidence around a
  method or benchmark;
- R&D teams evaluating conflicting findings before committing to an experiment;
- science analysts and technical writers who need provenance-backed summaries.

Secondary:

- reviewers and evaluators interested in claim-level knowledge graphs;
- builders studying LLM + graph + retrieval architectures;
- educators demonstrating how scientific consensus is represented.

### 3.4 Value proposition

- **Conflict-first discovery:** surface the disagreement, not just the documents.
- **Claim-level provenance:** every node can be traced to paper, section, and
  span.
- **Actionability:** a contradiction can become a minimal experiment design.
- **Graph-native exploration:** papers, claims, gaps, and relationships are
  visible together.
- **Local-first stack:** Neo4j, ChromaDB, Redis, and local embeddings can run on
  one machine; only generation requires an external LLM provider.

---

## 4. Current state

### 4.1 Snapshot

| Area | State (last verified) |
| :--- | :--- |
| **Live corpus** | 48 papers · 2,389 claims · 224 `CONTRADICTS` · 132 `SUPPORTS` · 93 `RELATED_TO` · 18 gaps · 36 experiment designs (graph counts last live-verified 2026-10-17; corpus existence re-confirmed 2026-10-23) |
| **API** | 23 routes total: 22 under `/api` plus `/healthz`; OpenAPI at `/docs` |
| **Auth** | Shared `AXION_API_KEY` on write/compute routes and job polling; fail-closed |
| **Background work** | RQ + Redis + separate worker; `202` + `GET /api/jobs/{job_id}`; cross-process verified |
| **LLM chain** | `groq` (`openai/gpt-oss-20b`) → `gemini` (`gemini-3.8-flash`, thinking disabled); Claude configured but not in the chain |
| **Tests** | 229 passed / 12 deselected offline; integration suite requires live services |
| **Frontend** | Next.js 16.2.6 (standalone), React 19, TypeScript 5.7.3, Tailwind v4; `pnpm lint` 0 errors (2 known warnings); `pnpm build` passes |
| **Evaluation** | Four-variant judge ablation complete on 286 reviewed pairs plus a 224-row audit; report, summary, chart data, and 1,144-line cache under `eval/results/` |
| **Deployment** | Five Compose services defined; not guaranteed running |
| **Demo posture** | Ready for a controlled, scripted demo; not ready for a hands-off live demo |

### 4.2 What the corpus counts actually mean

The number **224** is the count of `CONTRADICTS` relationships in Neo4j. It is
not the number of verified contradictions. The audit set contains **4 confirmed
human `CONTRADICTS` labels**; the other 220 audited detections were false
positives according to the labeling rubric. Treat 224 as "detected edges," and 4
as "confirmed positives in the evaluation set."

Likewise:

- **132 `SUPPORTS`** edges are model-generated, not human-verified.
- **93 `RELATED_TO`** edges link gaps to claims; they are not evidence of
  agreement.
- **18 gaps** are LLM-generated suggestions, not validated open problems.
- **36 experiment designs** are LLM proposals stored as JSON; none has been run.

### 4.3 Demo readiness

**Ready without a live LLM call:**

- offline evaluation walkthrough;
- graph and UI browsing over the existing corpus;
- API health check;
- frontend production build;
- reading the ablation report and cached results.

**Conditional:**

- live research queries (provider quota and latency);
- fresh ingestion (network, PDF availability, quota);
- new experiment designs (LLM call).

**Suggested scripted demo path:** start Docker Desktop → `docker compose up -d
--build` → wait for health → open `http://localhost:3000` → run one known query
→ show the contradiction view → open `eval/results/ablation_summary.md`. Do not
ingest papers or run a fresh multi-paper query on stage unless quota and latency
are known.

---

## 5. Architecture

### 5.1 High-level topology

```text
                         ┌─────────────────────────────────────┐
                         │            Browser                  │
                         │  Next.js client, six views, SWR     │
                         └───────────────┬─────────────────────┘
                                         │
                     public reads        │        credentialed writes
                     (direct)            │        (server proxy)
                                         ▼
                    ┌────────────────────────────────────────────┐
                    │  Next.js server (axion/)                   │
                    │  /api/backend/[...path] allowlist proxy    │
                    │  injects X-API-Key server-side             │
                    └───────────────────┬────────────────────────┘
                                        │ HTTP
                                        ▼
                    ┌────────────────────────────────────────────┐
                    │  FastAPI (api/main.py)                     │
                    │  reads, auth, rate limits, job submission  │
                    └───────┬───────────────┬────────────────────┘
                            │               │
              ┌─────────────▼───┐     ┌─────▼──────────────┐
              │ Neo4j 5.18      │     │ Redis 7.4 + RQ     │
              │ graph truth     │     │ queue + job state  │
              └─────────────┬───┘     └─────┬──────────────┘
                            │               │
              ┌─────────────▼───┐     ┌─────▼──────────────┐
              │ ChromaDB        │     │ Worker             │
              │ claims + chunks │◄────┤ jobs.worker        │
              └─────────────────┘     └─────┬──────────────┘
                                            │
                                  ┌─────────▼──────────┐
                                  │ LLM provider chain │
                                  │ Groq → Gemini      │
                                  └────────────────────┘
```

### 5.2 Components and responsibilities

| Component | Path | Responsibility | LLM? |
| :--- | :--- | :--- | :--: |
| arXiv client | `ingestion/arxiv_client.py` | Topic search, PDF download with retry/backoff | No |
| PDF parser | `ingestion/pdf_parser.py` | Text extraction, section splitting, 800-char chunks with 100-char overlap | No |
| Scheduler | `ingestion/scheduler.py` | Periodic/custom ingestion; enqueues jobs when a queue exists | No |
| Progress tracker | `ingestion/progress.py` | Ingestion status/logs for the UI, mirrored through Redis | No |
| Reader | `agents/reader.py` | Structured claim extraction and provenance | Yes |
| Contradiction agent | `agents/contradiction.py` | Candidate gate, relationship adjudication, decomposition guard | Yes |
| Gap finder | `agents/gap_finder.py` | Cluster gaps and future-work gaps (future-work path not wired into runner) | Yes |
| Experiment recommender | `agents/experiment_recommender.py` | Minimal resolving-experiment design | Yes |
| Confidence updater | `agents/confidence_updater.py` | Heuristic propagation from edge counts | No |
| Temporal agent | `agents/temporal.py` | Consensus evolution and dispute timelines | Yes |
| Citation agent | `agents/citation.py` | Semantic Scholar counts and citation weighting | No |
| Coordinator v2 | `agents/coordinator_v2.py` + planner/reflector/synthesizer | Multi-step question answering | Yes |
| Graph layer | `graph/neo4j_client.py`, `neo4j_queries.py`, `neo4j_schema.py` | Driver, Cypher, schema | No |
| Vector layer | `embeddings/store.py` | `claims` and `paper_chunks` collections | Local model |
| Job queue | `jobs/` | Durable queue, job store, worker, in-process fallback | No |
| LLM router | `llm.py` | Provider chain, retries, cooldown, optional cache | N/A |
| API | `api/main.py`, `api/models.py` | 22 `/api` routes + `/healthz` | N/A |
| Frontend | `axion/` | Six-view workspace, design system, server proxy | No |

### 5.3 Deployment topology

Docker Compose defines five services:

| Service | Image | Ports | Role |
| :--- | :--- | :--- | :--- |
| `neo4j` | `neo4j:5.18-community` | `127.0.0.1:7887` bolt, `127.0.0.1:7474` browser | Graph store; APOC enabled |
| `redis` | `redis:7.4-alpine` | `127.0.0.1:6389` | Job registry, queue, cross-process progress mirror |
| `api` | root `Dockerfile` | `8000` | FastAPI, single Uvicorn worker, enqueues heavy jobs |
| `worker` | same image as API | none | `python -m jobs.worker`; executes ingestion and query jobs |
| `web` | `axion/Dockerfile` | `3000` | Next.js standalone UI and server-side API proxy |

State is outside the containers:

- Neo4j data in the `neo4j_data` volume;
- ChromaDB vectors and downloaded PDFs in `./data` (bind mount);
- Hugging Face model weights in `hf_cache`;
- Redis job state in `redis_data`, TTL-bounded.

Operational constraints:

- Keep `worker` at **1 replica** while `SCHEDULER_ENABLED=true`.
- ChromaDB is opened by both API and worker over `./data`; SQLite/WAL handles
  this, but the graph remains the source of truth.
- `NEXT_PUBLIC_API_URL` is baked in at **build** time. Changing it requires
  `docker compose build web`.
- The web container needs `AXION_API_URL` and `AXION_API_KEY` so its proxy can
  reach the API and authenticate.

---

## 6. End-to-end pipelines

### 6.1 Ingestion

**Entry points:** `main.py --mode ingest`, `POST /api/ingestion/trigger`,
`POST /api/ingestion/custom`, or the scheduler.

1. **Search.** Query arXiv for a topic and select up to `n` papers.
2. **Download.** Fetch each PDF with retry/backoff. Existing PDFs can be reused.
3. **Parse.** Extract text, split sections, and chunk text into 800-character
   windows with 100-character overlap.
4. **Chunk embedding.** Store section chunks in ChromaDB's `paper_chunks`
   collection with arXiv ID and paper-year metadata.
5. **Claim extraction.** For the sections `Abstract`, `Introduction`, `Results`,
   `Experiments`, `Conclusion`, and `preamble`, ask the LLM for up to
   `MAX_CLAIMS_PER_PAPER` (8) falsifiable claims per section.
6. **Normalize.** Parse JSON robustly, skip unusable claims, and enforce minimum
   length. Structured fields include subject, predicate, object, metric,
   direction, conditions, and evidence span.
7. **Persist.** Create a `Claim` node, link it with `EXTRACTED_FROM` to the
   `Paper`, stamp `base_confidence` and `evidence_span`, and embed the claim into
   ChromaDB's `claims` collection.
8. **Fault isolation.** A failed section or paper is logged and skipped; the
   batch continues. A summary report is printed and recorded in metrics.

Important detail: `MAX_CLAIMS_PER_PAPER` is applied **per section**, not per
paper. A paper can therefore contribute substantially more than 8 claims.

### 6.2 Relation detection (contradictions and supports)

**Entry point:** `main.py --mode contradict`, or automatically after ingestion
depending on the caller.

1. Load all claims from Neo4j.
2. For each claim, retrieve the top 8 nearest claims from ChromaDB.
3. Skip the claim itself, already-checked pairs, and pairs whose cosine distance
   exceeds `CONTRADICTION_MAX_DISTANCE` (default **0.35**).
4. Run deterministic pre-checks: same claim ID and same paper are marked and
   skipped.
5. Send the pair to the LLM judge. The prompt asks for:
   - `relationship`: `CONTRADICTS`, `SUPPORTS`, or `UNRELATED`;
   - `explanation`;
   - `confidence`;
   - three decomposition booleans:
     - `same_phenomenon`;
     - `comparable_measurement`;
     - `opposite_outcome`.
6. **Demotion guard:** a `CONTRADICTS` verdict is accepted only if all three
   booleans are true. Otherwise it is demoted to `UNRELATED` with status
   `DEMOTED_BY_DECOMPOSITION`. This is a deterministic, testable constraint on
   LLM over-calling.
7. Persist non-`UNRELATED` verdicts as `CONTRADICTS` or `SUPPORTS` edges with
   explanation and confidence.
8. Recalculate confidence for all claims.

**The gate matters.** At the old value of 0.95, the gate was effectively inert:
100% of the 11,602 unique top-8 pairs passed. At 0.35, **42.6%** of pairs pass
while **80.2%** of claims still retain at least one candidate. Distance
distribution on the live index: p50 0.379, p90 0.538, p99 0.652, max 0.769.

### 6.3 Research query (Coordinator v2)

**Entry point:** `POST /api/query` → queued job → `GET /api/jobs/{id}`.

1. **Plan.** The planner decides what to retrieve: claims, contradictions, gaps,
   and whether the question is temporal.
2. **Retrieve.** Search ChromaDB for relevant claims; pull related
   contradictions and gaps from Neo4j.
3. **Reflect.** The reflector scores context sufficiency (0–10), writes an
   assessment, and may propose a refined query.
4. **Loop.** Repeat retrieve/reflect up to **3 iterations**, stopping early when
   the context is judged sufficient.
5. **Synthesize.** Produce a cited report with arXiv links, plus the plan,
   reflection log, iteration count, and raw context.
6. **Return.** The job result includes `report`, `raw`, `iterations`, `plan`,
   `reflection_log`, and `context`.

The coordinator is deliberately multi-step. The reflection trace is part of the
product surface, not just internal logging. Retrieval currently uses the
`claims` collection only; `paper_chunks` is populated during ingestion, but
`find_similar_chunks()` is not called by the coordinator.

### 6.4 Research gaps

There are two implemented strategies in `agents/gap_finder.py`:

- **Cluster gaps (`find_cluster_gaps`).** Sample up to 10 seed claims, retrieve
  six nearest neighbors per seed, ask the LLM what question the cluster circles
  but does not answer, require a confidence ≥ 0.5, and insert a `Gap` with
  `source="cluster"`.
- **Future-work gaps (`extract_future_work_gaps`).** Ask the LLM to extract open
  questions from a Future Work/Limitations section, then link each gap to five
  semantically similar claims with `source="future_work"`.

**Wiring caveat:** `run_gap_finding()` currently calls **only**
`find_cluster_gaps(n_clusters=10)`. `extract_future_work_gaps()` exists and is
tested but is not invoked by the runner. The README's claim that gaps are mined
from future-work sections describes an implemented function, not the active
batch path.

**Storage caveat:** the cluster path computes a confidence and filters on it, but
`insert_gap()` stores only `text` and `source`. No confidence is persisted, so the
API returns `null` for gap confidence and the UI does not display one.

### 6.5 Experiment recommendations

**Entry points:** `POST /api/experiments/{contradiction_id}/design` (direct, not
queued) or `main.py --mode experiments` for a batch.

The recommender asks for the **minimal experiment** that would settle a
contradiction, with mutually exclusive expected outcomes. The output includes:

- hypothesis A and hypothesis B;
- experiment title, dataset, models, metric, baseline, procedure, expected
  duration, and cost estimate;
- a decision rule;
- design confidence;
- caveats.

Designs are stored as JSON on the `CONTRADICTS` relationship
(`r.experiment_design`, `r.experiment_designed_at`), not as separate nodes. One
design per edge; there is no version history.

### 6.6 Temporal analysis

`agents/temporal.py` groups claims by `paper_year` and computes:

- consensus positions per year for a topic;
- claim counts and confidence by year;
- dispute timelines where contradictions appear across years.

This is descriptive, not causal. It depends on the `paper_year` stamped at
ingestion and on the topic matching in claim text.

### 6.7 Confidence propagation

`agents/confidence_updater.py` recomputes:

```text
new_confidence = base_confidence
               + 0.08 × supporting_edge_count
               − 0.12 × contradicting_edge_count
```

clamped to `[0.05, 0.98]`. It records support/contradiction counts and an update
timestamp. This is a transparent heuristic, not a probabilistic model. Because
the underlying edges are LLM-generated, confidence inherits their errors.

---

## 7. Code and agent inventory

| Path | Responsibility | Notes |
| :--- | :--- | :--- |
| `main.py` | CLI entry point | Modes: `ingest`, `contradict`, `gaps`, `experiments`, `query`, `confidence`, `citations`, `schedule`, `backup` |
| `config.py` | Central configuration | Reads `.env` through `python-dotenv`; model names, thresholds, paths |
| `llm.py` | LLM provider router | Groq → Gemini chain, retries, provider cooldown, optional cache |
| `api/main.py` | FastAPI app | 22 `/api` routes, auth dependency, rate limits, job wiring |
| `api/models.py` | Pydantic response models | Graph stats, claims, contradictions, experiments, gaps, coordinator output, temporal/confidence models |
| `agents/planner.py` | Query planning | Decides retrieval strategy |
| `agents/reflector.py` | Context sufficiency | Score, assessment, refined query |
| `agents/synthesizer.py` | Report generation | Cited synthesis |
| `agents/reader.py` | Claim extraction | Section-aware, structured, provenance |
| `agents/contradiction.py` | Relationship judge | Gate, prompt, guard, diagnostics |
| `agents/gap_finder.py` | Gap mining | Cluster path active; future-work path unwired |
| `agents/experiment_recommender.py` | Experiment design | JSON stored on edge |
| `agents/confidence_updater.py` | Confidence propagation | Heuristic |
| `agents/temporal.py` | Temporal views | Consensus and disputes |
| `agents/citation.py` | Citation weights | Semantic Scholar API |
| `graph/neo4j_client.py` | Driver | Connection and query helpers |
| `graph/neo4j_queries.py` | Cypher layer | Inserts, reads, stats |
| `graph/neo4j_schema.py` | Schema | Constraints and indexes |
| `graph/migrate_*.py` | One-off migrations | No general migration framework |
| `ingestion/arxiv_client.py` | arXiv search/download | Retry/backoff |
| `ingestion/pdf_parser.py` | PDF parsing | Sections and chunks |
| `ingestion/scheduler.py` | Periodic ingestion | APScheduler; enqueues jobs |
| `ingestion/progress.py` | Progress state | Redis mirror |
| `embeddings/store.py` | ChromaDB layer | `claims`, `paper_chunks` |
| `jobs/backend.py` | Job submission | RQ or inline |
| `jobs/store.py` | Job records | Redis-backed registry, TTL |
| `jobs/tasks.py` | Job functions | Ingestion and query execution |
| `jobs/worker.py` | Worker entry point | `python -m jobs.worker` |
| `utils/llm_parser.py` | JSON repair/parsing | Shared robust parser |
| `utils/llm_cache.py` | LLM response cache | Optional |
| `utils/metrics.py` | In-memory metrics | Reset on restart |
| `utils/logger.py` | Structured logging | Event logging |
| `eval/` | Evaluation harness | Gate measurement, judge ablation, metrics |
| `axion/` | Next.js frontend | Six views, design system, proxy |

---

## 8. Data model and storage

### 8.1 Neo4j nodes

| Node | Key | Properties | Populated? |
| :--- | :--- | :--- | :--: |
| `Paper` | `arxiv_id` unique | title, authors, year, abstract, citation count, metadata | Yes |
| `Claim` | `claim_id` unique | text, section, evidence_span, base_confidence, confidence, paper_year, subject, predicate, object_val, metric, direction, conditions, embedding_id | Yes |
| `Gap` | `gap_id` unique | text, source (`cluster` or `future_work`) | Yes |
| `Benchmark` | `name` unique | — | No |
| `Dataset` | `name` unique | — | No |
| `Method` | `name` unique | — | No |

`Benchmark`, `Dataset`, and `Method` constraints exist from earlier phases, but
no current ingestion path creates those nodes. Do not describe them as populated
entities.

### 8.2 Neo4j relationships

| Edge | Direction | Properties | Meaning |
| :--- | :--- | :--- | :--- |
| `EXTRACTED_FROM` | `Claim → Paper` | — | Provenance |
| `CONTRADICTS` | `Claim → Claim` | explanation, confidence, optional experiment JSON | Conflict |
| `SUPPORTS` | `Claim → Claim` | explanation, confidence | Supporting evidence |
| `RELATED_TO` | `Gap → Claim` | — | Gap-to-claim association |

`CONTRADICTS` and `SUPPORTS` are directional in storage but semantically treated
as pair-level findings. Duplicate pairs are deduplicated in the detection loop.
The three decomposition booleans are used for the runtime decision and by the
evaluation harness, but they are not persisted as edge properties.

### 8.3 Indexes and constraints

Unique constraints:

- `Paper.arxiv_id`
- `Claim.claim_id`
- `Gap.gap_id`
- `Benchmark.name`
- `Dataset.name`
- `Method.name`

Indexes:

- `Claim.paper_year`
- `Claim.section`
- `Claim.confidence`
- `Claim.subject`
- `Claim.metric`
- `Claim.direction`
- `Paper.year`

Schema creation is idempotent but **not** run by the API lifespan. The API only
verifies connectivity at startup. Create constraints/indexes explicitly with
`python -m graph.neo4j_schema` (the `main.py` CLI calls it on start).

### 8.4 ChromaDB collections

| Collection | Contents | Metadata | Embedding |
| :--- | :--- | :--- | :--- |
| `claims` | one document per claim | claim ID, arXiv ID, paper year, section, etc. | `all-MiniLM-L6-v2`, 384 dimensions |
| `paper_chunks` | section chunks (800 chars, 100 overlap) | arXiv ID, paper year, section, chunk index | same local model |

Embeddings are computed locally with `sentence-transformers`. No external
embedding API is required. Distance is treated as cosine distance
(`1 − cosine similarity`), which is what the gate thresholds are calibrated
against.

### 8.5 Redis keys

| Key | Contents |
| :--- | :--- |
| `rq:queue:axion` | pending RQ jobs |
| `axion:job:<id>` | job record: id, kind, status, timestamps, result, error |
| `axion:jobs:index` | sorted set of job IDs by creation time |
| ingestion progress keys | live status/log mirror for the UI |

Job records expire after `JOB_TTL_SECONDS` (default 86,400 seconds).

### 8.6 Filesystem layout

```text
data/
  papers/       downloaded PDFs
  db/chroma/    persistent ChromaDB store
  backups/      Neo4j backups (created by backup tooling)
```

### 8.7 Identifier caveat

Claims are inserted with `c.claim_id = elementId(c)`, and `claim_id` has a
uniqueness constraint. However, Neo4j element IDs are **not durable identifiers**
across database restore or re-creation. External links, saved contradiction IDs,
and experiment references can break if the graph is restored from a dump. For
stable external references, the project would need application-generated UUIDs.

---

## 9. API, authentication, and jobs

### 9.1 Basics

- Base URL locally: `http://localhost:8000`
- OpenAPI UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`
- Global rate limit: **60/minute per IP**, with tighter limits on compute routes.
- CORS origins come from `ALLOWED_ORIGINS`.

### 9.2 Authentication model

`require_write_access` guards every write/compute route and job polling:

- Accepted header: `X-API-Key: <AXION_API_KEY>`
- Legacy header: `X-Trigger-Secret: <TRIGGER_SECRET>`
- If **neither** `AXION_API_KEY` nor `TRIGGER_SECRET` is configured, guarded
  routes return **503** (fail closed).
- If a secret is configured but the supplied value is missing/wrong, the route
  returns **401**.
- The current dependency accepts `X-Trigger-Secret` on **every** guarded route,
  even though the docs describe it as an ingestion-only legacy header. Setting
  only `TRIGGER_SECRET` therefore keeps guarded routes enabled; prefer
  `AXION_API_KEY`.

Public read-only routes (stats, claims, contradictions, gaps, graph, temporal,
confidence reads, health) require no key. That means graph content is readable
by anyone who can reach the API; deploy behind a network boundary or reverse
proxy if that matters.

### 9.3 Endpoint table

All paths are relative to the base URL. "Key" means `X-API-Key` is required.

| Method | Path | Purpose | Key | Limit |
| :--- | :--- | :--- | :--: | :--- |
| GET | `/healthz` | Liveness; always 200 while serving | No | — |
| GET | `/api/health` | Readiness; 503 if Neo4j/Chroma unreachable | No | — |
| GET | `/api/metrics` | In-memory metrics summary | No | — |
| GET | `/api/stats` | Graph counts | No | — |
| GET | `/api/claims` | List claims (`limit`, `offset`) | No | — |
| GET | `/api/claims/{claim_id}/provenance` | Full provenance chain | No | — |
| GET | `/api/contradictions` | Contradictions (`min_confidence`, `limit`) | No | — |
| GET | `/api/experiments/{contradiction_id}` | Stored experiment design | No | — |
| POST | `/api/experiments/{contradiction_id}/design` | Design and store an experiment | Yes | 5/min |
| GET | `/api/gaps` | Gaps (`?source=`) | No | — |
| POST | `/api/query` | Enqueue a research query → `202` | Yes | 10/min |
| GET | `/api/jobs` | Recent jobs (`limit` ≤ 100) | Yes | — |
| GET | `/api/jobs/{job_id}` | Job status and result | Yes | — |
| GET | `/api/temporal/evolution` | Consensus evolution (`topic`, years) | No | — |
| GET | `/api/temporal/disputes` | Dispute timeline (`topic`) | No | — |
| GET | `/api/confidence/distribution` | Confidence histogram | No | — |
| GET | `/api/confidence/most-changed` | Largest confidence changes | No | — |
| POST | `/api/confidence/recalculate` | Recompute all claim confidence | Yes | 2/min |
| GET | `/api/ingestion/status` | Last run and running flag | No | — |
| GET | `/api/ingestion/progress` | Live progress and logs | No | — |
| POST | `/api/ingestion/trigger` | Enqueue one ingestion cycle → `202` | Yes | 2/min |
| POST | `/api/ingestion/custom` | Enqueue `{topic, limit}` (1–50) → `202` | Yes | 5/min |
| GET | `/api/graph` | Nodes/edges for the graph canvas | No | — |

Count: 22 routes under `/api` + `/healthz` = **23 total**.

### 9.4 Job contract

Long-running work uses a uniform contract:

```http
POST /api/query
Content-Type: application/json
X-API-Key: <AXION_API_KEY>

{"question": "Do larger models benefit more from chain-of-thought prompting?"}
```

```json
{"job_id": "b0fae4af-...", "status": "queued", "backend": "rq"}
```

Poll:

```http
GET /api/jobs/<job_id>
X-API-Key: <AXION_API_KEY>
```

```json
{
  "id": "...",
  "kind": "query",
  "status": "completed",
  "created_at": "...",
  "started_at": "...",
  "finished_at": "...",
  "result": { "...": "..." },
  "error": null,
  "backend": "rq"
}
```

Statuses: `queued → running → completed` or `failed`.

Two backends, one contract:

- **`rq`** when `REDIS_URL` is set: durable, executed by the worker, shared
  across processes.
- **`inline`** when Redis is absent: in-process thread pool, development only;
  jobs are lost on restart and invisible to other processes.

Other behavior:

- **Sanitized failures:** clients see `"Job failed. Check the server logs for
  details."`; the full exception is logged.
- **Ingestion exclusivity:** `active_ingestion_job()` reads the shared registry,
  so a second request returns **409** while one is active.
- **Retries:** RQ re-queues a job whose worker was killed mid-flight.
- **Timeouts:** `JOB_TIMEOUT_SECONDS` (default 1800) is passed to RQ. On Windows,
  RQ's `SimpleWorker` is used and per-job timeout enforcement is not available.
- **Payload hygiene:** internal `_payload` is stripped from API responses by
  `public_view`.

Not every compute route is a job. Experiment design and confidence recalculation
are synchronous, rate-limited POSTs. Only research queries and ingestion are
queued.

### 9.5 Frontend proxy allowlist

The browser never holds the API key. Credentialed calls go through
`axion/app/api/backend/[...path]/route.ts`, which:

- matches an explicit method + path allowlist:
  - `POST /query`
  - `POST /experiments/{id}/design`
  - `POST /confidence/recalculate`
  - `POST /ingestion/trigger`
  - `POST /ingestion/custom`
  - `GET /jobs/{id}`
- injects `X-API-Key` from the server-only `AXION_API_KEY`;
- returns **404** for anything else, so it cannot be used as an open proxy;
- returns **503** if the server key is missing;
- uses `AXION_API_URL` or `NEXT_PUBLIC_API_URL` as the upstream.

Public reads are called directly from the browser, which is why
`NEXT_PUBLIC_API_URL` is public.

---

## 10. Frontend and design system

### 10.1 Stack

| Item | Version / choice |
| :--- | :--- |
| Framework | Next.js **16.2.6**, App Router, standalone output |
| UI runtime | React **19** |
| Language | TypeScript **5.7.3** |
| Styling | Tailwind CSS **v4** (`@tailwindcss/postcss`) |
| Package manager | pnpm **10.22.0** (pinned via `packageManager`) |
| Data fetching | SWR **2.4.1** |
| Graph rendering | `react-force-graph-2d` |
| Markdown | `react-markdown` |
| Primitives | Radix UI (dialog, collapsible, slider, tooltip, progress, label, slot) |
| Icons | `lucide-react` |
| Analytics | `@vercel/analytics` |

### 10.2 Views

Navigation is a collapsible rail with six items, and keyboard shortcuts `1`–`6`:

1. **Research** — query panel, recent queries, report rendering.
2. **Knowledge Graph** — force-directed graph of papers, claims, and gaps.
3. **Contradictions** — list and detail, with experiment design action.
4. **Research Gaps** — gap list with source filter.
5. **Timeline** — consensus/dispute views by year.
6. **Graph Evolution** — confidence distribution and most-changed claims.

A command bar (`⌘K` / `Ctrl-K`) provides global query entry. Recent queries are
stored in browser `localStorage` under `axion-query-history`, limited to 10.

### 10.3 Design system: Cobalt Grid

The frontend uses a custom editorial/technical design language:

| Token | Value |
| :--- | :--- |
| Paper background | `#F0EBDE` |
| Ink / primary | `#1F2BE0` |
| Soft ink | `#5560E5` |
| Grid line | `rgba(31, 43, 224, 0.1)` |
| Display font | Newsreader (serif) |
| Interface font | Hanken Grotesk |
| Mono font | DM Mono |
| Radius | `0px` (sharp corners) |
| Grid size | `24px` |

The visual language is deliberately print-like: warm paper, blue ink, visible
grid, hairlines, no rounded cards. It is a strong differentiator and should be
preserved in new UI work.

### 10.4 Client behavior

- Reads use SWR with refresh intervals where appropriate (health every 60 s).
- Job submission goes through the proxy; polling uses `GET /jobs/{id}` every
  2 s with a 30-minute client timeout (matching the backend job timeout).
- The UI shows queued/running states and sanitized errors.
- The health indicator in the nav rail is a real `/api/health` call, not a mock.
- The graph view is client-only; the app uses `useIsClient` to avoid SSR issues.

### 10.5 Build and lint

```bash
cd axion
pnpm install --frozen-lockfile
pnpm lint
pnpm build
```

Last recorded state: lint passes with 0 errors and 2 known warnings; production
build passes. CI runs both.

---

## 11. Configuration

All backend configuration is read from environment variables, typically loaded
from the repo-root `.env` by `config.py`. `.env` is gitignored. `.env.example` is
the template and contains placeholders only. Never commit or paste real keys.

### 11.1 Required for a working stack

| Variable | Why |
| :--- | :--- |
| `NEO4J_PASSWORD` | Neo4j refuses to start without it; API cannot connect |
| `AXION_API_KEY` | Guarded routes fail closed (503) when neither it nor `TRIGGER_SECRET` is set; this is the primary secret |
| `GROQ_API_KEY` and/or `GEMINI_API_KEY` | Without at least one, ingestion and queries fail at the first LLM call |

### 11.2 Full reference

| Variable | Default | Meaning |
| :--- | :--- | :--- |
| `NEO4J_URI` | `bolt://localhost:7887` | Neo4j connection |
| `NEO4J_USERNAME` | `neo4j` | Neo4j user |
| `NEO4J_PASSWORD` | — | Neo4j password |
| `NEO4J_CONTAINER_NAME` | `axion_neo4j` | Container name for backup tooling |
| `GROQ_API_KEY` | — | Groq credential |
| `GEMINI_API_KEY` | — | Gemini credential |
| `ANTHROPIC_API_KEY` | — | Claude credential (configured, not in chain) |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Fallback model |
| `GEMINI_THINKING_BUDGET` | `0` | Disable Gemini 3.x hidden thinking tokens |
| `LLM_CACHE_ENABLED` | `false` | In-process LLM response cache |
| `LLM_PROVIDER_COOLDOWN_SECONDS` | `300` | Bench time after a hard provider failure |
| `CONTRADICTION_MAX_DISTANCE` | `0.35` | Max cosine distance sent to the judge |
| `AXION_API_KEY` | — | Shared secret for writes and job polling |
| `TRIGGER_SECRET` | — | Legacy alternative accepted on **all** guarded routes; leave empty |
| `REDIS_URL` | — (inline jobs) | Queue and shared job state |
| `JOB_TTL_SECONDS` | `86400` | Job record retention |
| `JOB_TIMEOUT_SECONDS` | `1800` | RQ job timeout |
| `SCHEDULER_ENABLED` | `false` | Run periodic ingestion in the API process |
| `SCHEDULER_INTERVAL_HOURS` | `6` | Scheduler interval |
| `SCHEDULER_PAPERS_PER_RUN` | `5` | Papers per scheduler cycle |
| `ALLOWED_ORIGINS` | `http://localhost:3000,http://localhost:5173` | CORS allowlist |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Public API URL baked into the frontend at build time |
| `AXION_API_URL` | `http://api:8000` (Compose) | Server-side proxy target |
| `LOG_LEVEL` | `INFO` | Python log level |

### 11.3 LLM behavior

| Setting | Value |
| :--- | :--- |
| Chain | `["groq", "gemini"]` |
| Groq model | `openai/gpt-oss-20b` (reasoning effort low) |
| Gemini model | `gemini-3.8-flash`, thinking budget 0 |
| Claude | `claude-sonnet-4-20250514` configured but not in the chain |
| Transient retries | 2 s / 5 s / 10 s |
| Rate limits | fall through to next provider |
| Hard failure | provider benched for 300 s |
| Exhaustion | raises `All LLM providers exhausted after retries. Chain tried: [...]` |

If every provider is unavailable, jobs fail cleanly and the error is logged.
Keys being present does not guarantee live quota.

---

## 12. Running Axion

### 12.1 Docker Compose (supported path)

```bash
cp .env.example .env          # fill in passwords and keys
docker compose up -d --build
docker compose ps             # neo4j/redis/api/web healthy; worker up
```

Endpoints:

- Web UI: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`
- Neo4j Browser: `http://localhost:7474` (bolt on `7887`)
- Redis: `127.0.0.1:6389`

Stop:

```bash
docker compose down            # keep volumes
docker compose down -v         # delete Neo4j/Redis/HF volumes
```

Logs:

```bash
docker compose logs -f api
docker compose logs -f worker
```

Notes:

- The Docker daemon must be running. At the last operational check it was
  stopped.
- On a fresh Neo4j volume, create constraints/indexes explicitly:
  `docker compose exec api python -m graph.neo4j_schema`.
- Neo4j and Redis are loopback-bound; API and web are published on all
  interfaces.
- `NEXT_PUBLIC_API_URL` changes require rebuilding the web image.
- Keep the worker at one replica when the scheduler is enabled.

### 12.2 Local development (no Docker for app processes)

```bash
python -m venv venv
venv\Scripts\activate                 # Windows
pip install -r requirements.txt -r requirements-dev.txt

docker compose up -d neo4j redis      # datastores only

python -m uvicorn api.main:app --reload --port 8000
```

In a second terminal:

```bash
cd axion
pnpm install
pnpm dev
```

Optional worker (third terminal):

```bash
python -m jobs.worker
```

Without `REDIS_URL`, the API runs jobs inline in a thread pool. Without a worker
but with Redis, jobs stay `queued`.

Local frontend environment (`axion/.env.local`):

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
AXION_API_KEY=<same value as the root .env>
```

### 12.3 CLI

```bash
python main.py --mode ingest --query "chain of thought prompting" --n 10
python main.py --mode contradict       # judge pairs and recalc confidence
python main.py --mode gaps             # cluster gap discovery
python main.py --mode experiments      # design experiments for contradictions
python main.py --mode query            # run a coordinator query from the shell
python main.py --mode confidence       # recompute confidence
python main.py --mode citations        # refresh citation weights
python main.py --mode schedule         # one scheduler cycle in the foreground
python main.py --mode backup           # Neo4j backup (shells out to Docker)
```

### 12.4 Verification commands

```bash
# Offline test suite (no live services required)
venv\Scripts\python.exe -m pytest -q

# Gate measurement (offline, deterministic, no LLM, no writes)
python eval/measure_gate.py

# Queue/auth smoke test (submits a real query; consumes LLM quota)
python scripts/queue_smoke.py

# Integration tests (need live Neo4j/ChromaDB)
pytest -m integration
```

### 12.5 Common failure modes

| Symptom | Likely cause |
| :--- | :--- |
| `ModuleNotFoundError: No module named 'arxiv'` | Dependencies not installed; `arxiv` **is** pinned in `requirements.txt` as of this verification |
| Guarded routes return 503 | Neither `AXION_API_KEY` nor `TRIGGER_SECRET` is set on the API |
| Guarded routes return 401 | Missing or wrong `X-API-Key` |
| Jobs stay `queued` | No worker running, or `REDIS_URL` points somewhere else |
| `All LLM providers exhausted` | Provider quota/keys; check logs and `.env` |
| Neo4j container restarts | `NEO4J_PASSWORD` missing or invalid; the healthcheck derives it from `NEO4J_AUTH` |
| Frontend cannot reach API | `NEXT_PUBLIC_API_URL` baked at build time; rebuild `web` |
| Chroma lock/contention | Too many worker replicas sharing `./data`; scale down |
| Graph view empty | No data ingested, or `/api/graph` returned an error |

---

## 13. Testing, CI, and evaluation

### 13.1 Offline test suite

Command:

```bash
venv\Scripts\python.exe -m pytest -q
```

Last verified result (2026-10-24):

```text
229 passed, 12 deselected, 1 warning in 9.54s
```

`pytest.ini` sets `testpaths = tests` and `addopts = -v -m "not integration"`, so
the default run excludes tests that need live services. The 12 deselected tests
are the integration suite.

Coverage areas include agents, API endpoints, regressions, claims, evaluation
metrics, ingestion, jobs, the LLM router, Neo4j queries, and phase-4/5 behavior.
Evaluation-metric tests live in `tests/test_eval_metrics.py`.

### 13.2 Integration tests

```bash
pytest -m integration
```

These require live Neo4j and ChromaDB. The last recorded full integration run
passed 12 tests against live services. They are not part of default CI.

### 13.3 CI

`.github/workflows/ci.yml` runs on pushes and pull requests to `main`:

- **Backend:** Python 3.11, install `requirements-dev.txt`, run `pytest -q`.
- **Frontend:** pnpm 10, Node 20, `pnpm install --frozen-lockfile`, `pnpm lint`,
  `pnpm build`.

Integration tests and Docker builds are not part of CI.

### 13.4 Evaluation harness

`eval/` is a standalone harness for measuring the contradiction pipeline:

| File | Purpose |
| :--- | :--- |
| `eval/dataset.py` | Load and validate labeled pairs |
| `eval/predictors.py` | Variant predictors (gate, prompt, guard, model) |
| `eval/judge_ablation.py` | Four-variant ablation runner |
| `eval/metrics.py` | Precision, recall, F1, Wilson intervals |
| `eval/measure_gate.py` | Offline distance/pass-rate measurement |
| `eval/run_eval.py` | End-to-end evaluation entry point |
| `eval/baseline_llm_eval.py` | Baseline comparison |
| `eval/mine_contradiction_candidates.py` | Candidate mining |
| `eval/build_ablation_summary.py` | Report/summary generation |
| `eval/results/` | Reports, summary, chart data, cache |

Key datasets:

- `eval/Data/axion_pairs.csv`: 286 cross-paper pairs — 4 `CONTRADICTS`,
  11 `SUPPORTS`, 271 `UNRELATED`.
- `eval/Data/contradicts_review_labeled.csv`: 224 audited production
  `CONTRADICTS` detections — 4 confirmed contradictions, 11 supports, 209
  unrelated (220 verified false positives).

Dataset caveats:

- Only 4 confirmed contradictions. Any precision/recall estimate is extremely
  wide and unstable.
- 62 rows in the full set come from `labeled_pairs_cleaned` and have unverified
  negative provenance; they affect only secondary full-set metrics.
- The audit's "old judge" is the production agent that wrote the original edges,
  not variant A's pre-change setup.
- The original 1.8% production precision figure came from an older
  `llama-3.1-8b-instant` run at gate 0.95 with the old prompt. The current model
  swap itself is not measured by that figure.

### 13.5 Four-variant ablation

Variants:

| Variant | Gate | Prompt | Guard | Model |
| :--- | ---: | :--- | :--- | :--- |
| A | 0.95 | old | off | `groq/openai/gpt-oss-20b` |
| B | 0.35 | old | off | `groq/openai/gpt-oss-20b` |
| C | 0.35 | current | on | `groq/openai/gpt-oss-20b` |
| D | 0.35 | current | on | `gemini/gemini-3.8-flash` |

Primary audit result (224 rows; 220 false positives, 4 confirmed positives):

| Variant | FPs stopped / 220 | FP suppression | TPs kept / 4 | TP retention |
| :--- | ---: | ---: | ---: | ---: |
| A | 208 | 94.5% | 3 | 75.0% |
| B | 219 | 99.5% | 0 | 0% |
| C | 220 | 100% | 1 | 25.0% |
| D | 220 | 100% | 0 | 0% |

Secondary full-set result (286 rows):

| Variant | Flagged | TP | FP | FN | Precision | Recall | Macro F1 |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 15 | 3 | 12 | 1 | 0.200 | 0.750 | **0.532** |
| B | 1 | 0 | 1 | 4 | 0.000 | 0.000 | 0.354 |
| C | 1 | 1 | 0 | 3 | 1.000 | 0.250 | 0.514 |
| D | 0 | 0 | 0 | 4 | n/a | 0.000 | 0.380 |

Interpretation:

- The gate at 0.35 is doing most of the false-positive suppression (190 of 220
  stopped by gate in B/C/D).
- The current prompt accounts for the one additional audit false positive
  stopped by C relative to B. The decomposition guard demoted no audit false
  positives in this run, so its measured contribution on this dataset is zero.
- Variant A has the best macro F1 in this pilot, largely because it keeps 3 of 4
  positives; its precision is 20%.
- Variant C is the current code configuration (gate 0.35, current prompt,
  guard on) and achieves the highest FP suppression, but keeps only 1 of 4
  positives.
- Pair `124` is a confirmed contradiction at distance 0.5019, above the 0.35
  gate, so B/C/D never see it. This is the core trade-off.
- Variant D (Gemini) is an alternative judge from another provider, not assumed
  stronger.

**Do not present this as a stable ranking or a production precision claim.** It
is a small, pre-registered pilot with four positives. It is useful for showing
the gate/guard trade-off and for reproducibility, not for claiming the system is
"95% accurate."

### 13.6 What a valid evaluation would require

- A substantially larger set of human-confirmed contradictions across topics.
- Double annotation or adjudication for labels.
- A held-out split that was not used to tune the gate, prompt, or guard.
- Per-class confidence intervals and error analysis.
- Separate measurement of claim extraction quality (the judge can only be as
  good as the claims it sees).
- End-to-end evaluation from ingestion to answer, not only pair classification.

---

## 14. Security posture

### 14.1 Controls present

- **Fail-closed shared-key auth** on writes/computes/job polling.
- **Server-side proxy allowlist** in Next.js; the API key never reaches the
  browser bundle.
- **Public/private split:** reads are public, mutations and expensive calls are
  guarded.
- **Rate limits:** global 60/min per IP; tighter per-route limits.
- **CORS allowlist** via `ALLOWED_ORIGINS`.
- **Loopback-bound datastores** in Compose (Neo4j, Redis), reducing LAN exposure.
- **Sanitized job errors** so internal exceptions are not returned to clients.
- **Payload stripping** (`public_view`) on job responses.
- **Secrets via environment**; `.env` is gitignored and `.env.example` contains
  placeholders.
- **Dependency pinning** in `requirements.txt` and the pnpm lockfile.
- **Prompt/response caching is opt-in** and off by default.

### 14.2 Open risks

- **No user accounts or roles.** One shared key means no per-user revocation,
  attribution, or quota.
- **No TLS in the repository.** Terminate TLS at a reverse proxy/load balancer.
- **Read endpoints are unauthenticated.** Anyone with network access can read
  the graph and claim text.
- **API and web publish on all interfaces** in Compose; Neo4j/Redis are loopback
  only, but the API is not.
- **Prompt injection via papers.** PDFs are untrusted input; a malicious paper
  could contain instructions that influence extraction or synthesis. There is no
  content sanitization or instruction hierarchy beyond prompt wording.
- **No audit log** for writes, experiment designs, or ingestion triggers.
- **No CSRF protection** beyond same-origin assumptions and CORS; the proxy is
  same-origin, but a compromised frontend could still act with the server key.
- **No secrets rotation mechanism**; changing `AXION_API_KEY` requires updating
  API and web environments.
- **No vulnerability scanning or SBOM** in CI.
- **LLM data leaves the machine.** Prompts include claim text and paper content;
  provider retention policies apply.
- **Shared Redis has no password** in Compose (loopback-bound, but still).
- **In-memory metrics** are unauthenticated and reset on restart; not a security
  boundary, but avoid exposing them publicly.

### 14.3 Deployment guidance

For anything beyond a local demo:

1. Put the API and web behind a TLS-terminating reverse proxy.
2. Restrict read endpoints at the network layer or add auth.
3. Use a unique, high-entropy `AXION_API_KEY`; rotate it.
4. Do not publish Neo4j or Redis ports beyond loopback.
5. Add per-user auth and quotas before multi-tenant use.
6. Add audit logging for mutations.
7. Treat all paper content as untrusted.
8. Back up Neo4j and Chroma consistently; test restores, remembering that
   element IDs are not durable.

---

## 15. Known limitations and documentation drift

### 15.1 Product and correctness limitations

- **Contradiction precision is unproven.** 224 detected edges, 4 confirmed
  positives. The audit found 220 false positives among 224 old detections.
- **Claim extraction is unvalidated.** There is no measured precision/recall for
  claims versus source text, and no inter-annotator study.
- **Gap quality is unvalidated.** Gaps are LLM suggestions; confidence is not
  stored; the future-work path is not wired into the runner.
- **Experiment designs are proposals.** None has been executed; feasibility and
  cost estimates are LLM-generated.
- **Confidence is heuristic.** It propagates edge counts, not evidence quality,
  sample size, or study design.
- **Temporal analysis is descriptive.** It depends on paper year and topic
  matching; it does not model publication bias or citation dynamics causally.
- **arXiv only.** No PubMed, Semantic Scholar full text, OpenAlex, or
  institutional repositories. No non-English handling. No OCR for scanned PDFs.
- **No human-in-the-loop corrections.** Users cannot confirm, reject, or relabel
  a contradiction, claim, or gap in the UI.
- **No systematic-review workflow.** No screening, dual extraction, risk-of-bias,
  or meta-analysis.
- **Not a substitute for domain expertise.** Outputs are research aids.

### 15.2 Engineering limitations

- **Single shared API key; no accounts.**
- **No TLS, no HA, no horizontal API scaling.**
- **In-memory metrics** reset on restart.
- **No migration framework.** Schema is idempotent; data migrations are ad hoc
  scripts in `graph/`.
- **Neo4j element IDs as claim/gap IDs** are not durable across restore.
- **One experiment design per contradiction**, no versioning.
- **No export or streaming.** Reports are returned as job results; there is no
  PDF/DOCX/BibTeX export and no token streaming.
- **Query history is browser-local** (`localStorage`), not shared or searchable.
- **Graph endpoint returns the graph for canvas rendering**; large corpora will
  need pagination/filtering.
- **Scheduler requires a single API process** and worker replica constraints.
- **Windows worker uses `SimpleWorker`**, so per-job timeouts are not enforced.
- **ChromaDB is shared by two processes** over a bind mount; SQLite/WAL is fine
  for this scale but not a clustered vector store.
- **LLM quota is an external dependency.** Provider failures surface as failed
  jobs.
- **No background re-indexing or embedding migration** when the model changes.
- **Docs lag code** in several places (below).

### 15.3 Data limitations

- 48 papers is a small, AI/ML-centric corpus.
- 2,389 claims are unevenly distributed across papers and sections.
- 224 contradiction edges are mostly unverified.
- 18 gaps and 36 experiment designs are generated artifacts, not validated
  results.
- Citation counts depend on Semantic Scholar availability and coverage.
- Paper year is used as a proxy for chronology; publication lag and preprint
  versions are not modeled.

### 15.4 Documentation drift worth knowing

These are real inconsistencies verified against the code on 2026-10-24. Prefer
this brief and the code over the older statements.

| Older statement | Actual state |
| :--- | :--- |
| README says the API has **21 routes** in places. | `api/main.py` defines **22 `/api` routes + `/healthz` = 23**. `PROJECT_STATUS_NOW.md` is correct. |
| README says `arxiv` is **not** in `requirements.txt`. | `arxiv==4.0.0` **is** pinned in `requirements.txt`. The troubleshooting note is stale. |
| Some docs say the schema is created automatically at API startup. | The API lifespan verifies Neo4j/Chroma connectivity but does **not** call `init_neo4j()`. Run `python -m graph.neo4j_schema` (or use the CLI). |
| README says Coordinator v2 runs **synchronously in the request**. | `POST /api/query` enqueues a job and returns `202`; the coordinator runs in the worker (or inline fallback). |
| README says gaps are mined from **future-work and limitation statements**. | `extract_future_work_gaps()` exists, but `run_gap_finding()` calls only `find_cluster_gaps()`. The active batch path is cluster gaps. |
| Docs/UI describe gap sources as `semantic` and `llm_synthesized`. | The current code stores gaps with `source="cluster"` or `"future_work"`. The API defaults a missing source to `llm_synthesized`. The UI filter options (`semantic`, `llm_synthesized`) therefore do not match the current code's values and may return zero results. |
| Some docs say `X-Trigger-Secret` applies only to ingestion triggers. | `require_write_access` accepts it on **every** guarded route. Use `AXION_API_KEY` and leave `TRIGGER_SECRET` unset unless you need the legacy path. |
| Some docs imply the 224 edges are "contradictions." | They are auto-detected `CONTRADICTS` edges; only 4 are human-confirmed. |
| Some docs imply all compute is queued. | Research queries and ingestion are queued; experiment design and confidence recalculation are synchronous, rate-limited POSTs. |
| Some docs imply `Benchmark`/`Dataset`/`Method` are part of the graph. | Constraints exist, but no ingestion code populates those nodes. |
| `PROJECT_STATUS_NOW.md` snapshot says `main` @ `a273b5d`. | Current HEAD at verification is `0da2919`; the status snapshot predates the latest commits. |

### 15.5 Claims to avoid in a README, demo, or pitch

Avoid:

- "Axion detects contradictions with high precision."
- "The system has 224 validated contradictions."
- "The evaluation proves the judge is 95% accurate."
- "Axion is production-ready / multi-tenant / secure by default."
- "Gaps are mined from future work" without the wiring caveat.
- "The graph contains benchmarks, datasets, and methods" as populated data.
- "The frontend has a full authentication system."

Prefer:

- "Axion surfaces candidate contradictions for expert review; the current pilot
  has four confirmed positives."
- "The 0.35 gate substantially reduces false positives on a small audited set;
  precision at scale is not yet established."
- "Axion is a self-hosted research prototype with a working end-to-end pipeline."
- "The graph stores papers, claims, gaps, and their relationships."

---

## 16. Roadmap

Ordered by leverage for credibility, not by ease.

### P0 — Make the core claim defensible

1. **Expand the human-labeled contradiction set.** Target hundreds of confirmed
   positives across topics; double-annotate and adjudicate.
2. **Re-run the ablation on a held-out set.** Keep the gate/prompt/guard frozen
   during evaluation; report per-class intervals and error analysis.
3. **Measure claim extraction quality.** Sample claims against source spans;
   measure precision, recall, and provenance accuracy.
4. **Add a human review queue** for contradictions, claims, and gaps (confirm /
   reject / edit), with audit history.

### P1 — Close product gaps

5. **Wire future-work gap extraction** into `run_gap_finding()` and persist gap
   confidence.
6. **Fix gap source naming** across storage, API, and UI (`cluster`,
   `future_work`), or migrate data and expose a stable taxonomy.
7. **Add export and sharing** for reports (Markdown/PDF/BibTeX) and graph slices.
8. **Add filtering/pagination** to the graph endpoint and UI for larger corpora.
9. **Add per-user auth, quotas, and audit logging** before any shared deployment.

### P2 — Harden operations

10. **TLS/reverse-proxy deployment recipe**, secrets rotation, and network
    policies.
11. **Persistent metrics** (Prometheus) and dashboards; structured request IDs.
12. **Migration framework** for Neo4j and Chroma, plus embedding-model versioning.
13. **Durable, application-generated IDs** instead of element IDs.
14. **Backup/restore drills** and data consistency checks between Neo4j and
    Chroma.
15. **Prompt-injection defenses** and content sanitization for untrusted PDFs.

### P3 — Expand the science

16. **More sources** (PubMed, OpenAlex, Semantic Scholar full text) and
    non-English/OCR handling.
17. **Condition-aware contradiction modeling** (dataset, metric, model scale,
    evaluation setup) beyond three booleans.
18. **Evidence-weighted confidence** instead of edge-count heuristics.
19. **Experiment tracking**: link proposed designs to executed results.
20. **Longitudinal consensus analysis** with citation and publication-bias
    modeling.

---

## 17. Repository map

```text
schimesh/
├── agents/                  # LLM agents and analysis logic
│   ├── planner.py
│   ├── reflector.py
│   ├── synthesizer.py
│   ├── coordinator_v2.py
│   ├── reader.py
│   ├── contradiction.py
│   ├── gap_finder.py
│   ├── experiment_recommender.py
│   ├── confidence_updater.py
│   ├── temporal.py
│   └── citation.py
├── api/
│   ├── main.py              # FastAPI app, 22 /api routes + /healthz
│   └── models.py            # Pydantic models
├── axion/                   # Next.js frontend (Cobalt Grid)
│   ├── app/                 # App Router pages, layout, proxy route
│   ├── components/axion/    # six-view components
│   ├── components/cg/       # design-system primitives
│   ├── components/ui/       # Radix/Tailwind primitives
│   ├── lib/api-client.ts    # reads, proxy writes, job polling
│   └── types/axion.ts       # shared types
├── data/                    # PDFs, Chroma store, backups (gitignored)
├── embeddings/store.py      # ChromaDB layer
├── eval/                    # gate measurement + judge ablation
│   ├── Data/                # labeled pairs
│   └── results/             # reports, summary, cache
├── graph/
│   ├── neo4j_client.py
│   ├── neo4j_queries.py
│   ├── neo4j_schema.py
│   └── migrate_*.py
├── ingestion/
│   ├── arxiv_client.py
│   ├── pdf_parser.py
│   ├── scheduler.py
│   └── progress.py
├── jobs/                    # RQ backend, store, tasks, worker
├── scripts/queue_smoke.py   # auth + queue smoke test
├── tests/                   # 229 offline tests + integration
├── utils/                   # logging, metrics, JSON parsing, cache
├── config.py                # environment configuration
├── llm.py                   # provider router
├── main.py                  # CLI
├── docker-compose.yml       # five-service stack
├── Dockerfile               # API/worker image
├── requirements.txt
├── requirements-dev.txt
├── pytest.ini
├── .env.example
├── README.md
├── PROJECT_BRIEF.md         # this file
├── PROJECT_INFO.md
├── PROJECT_STATUS_NOW.md
├── PROJECT_STATE.md
├── AI_CONTEXT.md
├── AXION_SPEC.md
├── AXION_MASTER_CONTEXT.md
├── FILE_MAP.md
├── FRONTEND_HANDOVER.md
└── progress.md
```

### Key entry points

- **Run the API:** `uvicorn api.main:app --reload --port 8000`
- **Run the worker:** `python -m jobs.worker`
- **Run the UI:** `cd axion && pnpm dev`
- **Run the CLI:** `python main.py --mode ...`
- **Initialize schema:** `python -m graph.neo4j_schema`
- **Run tests:** `pytest`
- **Run eval:** `python eval/judge_ablation.py` (see `eval/README.md`)
- **Measure gate:** `python eval/measure_gate.py`

---

## 18. Onboarding reading order

For a new engineer:

1. **This brief** — product, architecture, and caveats.
2. `PROJECT_STATUS_NOW.md` — operational runbook and current state.
3. `AI_CONTEXT.md` — architectural mental model and folder responsibilities.
4. `api/main.py` — actual routes, auth, and response shapes.
5. `agents/contradiction.py` — the core quality-sensitive path.
6. `agents/reader.py` — how claims and provenance are created.
7. `agents/coordinator_v2.py` — the query loop.
8. `graph/neo4j_queries.py` and `graph/neo4j_schema.py` — data model in practice.
9. `jobs/` — queue contract and failure behavior.
10. `axion/app/page.tsx` and `axion/lib/api-client.ts` — UI wiring.
11. `eval/results/judge_ablation.md` — what the evaluation does and does not show.
12. `progress.md` — remediation history and open items.
13. `PROJECT_INFO.md` — full capability inventory (use with the drift caveats).
14. `AXION_SPEC.md` / `AXION_MASTER_CONTEXT.md` — background and design history;
    check against code before quoting metrics.

For a reviewer:

1. This brief, sections 1, 4, 13, 14, and 15.
2. `eval/results/judge_ablation.md` and `eval/README.md`.
3. `api/main.py` auth and job routes.
4. `docker-compose.yml` and `.env.example`.
5. `README.md` limitations, keeping the drift table in mind.

For a frontend contributor:

1. `FRONTEND_HANDOVER.md`.
2. `axion/components/axion/nav-rail.tsx` and `app/page.tsx`.
3. `axion/app/globals.css` (Cobalt Grid tokens).
4. `axion/lib/api-client.ts` (proxy and job polling).
5. `axion/app/api/backend/[...path]/route.ts` (allowlist).

---

## 19. Glossary

| Term | Meaning |
| :--- | :--- |
| **Claim** | An atomic, falsifiable statement extracted from a paper section, with provenance. |
| **Provenance** | The link from a claim to its paper, section, and evidence span. |
| **Evidence span** | A short quote or close paraphrase supporting a claim. |
| **CONTRADICTS** | A judged relationship where two claims conflict under comparable conditions. |
| **SUPPORTS** | A judged relationship where one claim provides supporting evidence for another. |
| **UNRELATED** | A judged relationship with no substantive support or conflict. |
| **Decomposition guard** | Deterministic rule requiring `same_phenomenon`, `comparable_measurement`, and `opposite_outcome` before a `CONTRADICTS` verdict counts. |
| **Gate** | Maximum cosine distance for a claim pair to reach the LLM judge (`CONTRADICTION_MAX_DISTANCE`, default 0.35). |
| **Candidate pair** | A top-8 nearest-neighbor claim pair that passes deduplication and the gate. |
| **Gap** | An LLM-generated open research question linked to related claims. |
| **Cluster gap** | A gap derived from a cluster of semantically similar claims. |
| **Future-work gap** | A gap extracted from a paper's Future Work/Limitations text. |
| **Coordinator v2** | The plan → retrieve → reflect (≤3) → synthesize query pipeline. |
| **Reflection** | The sufficiency assessment that decides whether to retrieve again. |
| **Job** | A queued unit of work (ingestion or research query) with a pollable record. |
| **RQ** | Redis Queue, the durable job queue used when `REDIS_URL` is set. |
| **Inline backend** | In-process thread-pool fallback when Redis is absent. |
| **Cobalt Grid** | The frontend design language: warm paper, cobalt ink, visible grid, sharp corners. |
| **Ablation** | The four-variant evaluation (A/B/C/D) of gate, prompt, guard, and model. |
| **Wilson interval** | A binomial confidence interval used for suppression/retention rates. |
| **Macro F1** | Unweighted mean of per-class F1 scores. |
| **Pilot** | The current evaluation, too small to support production claims. |

---

## 20. Bottom line

Axion is a credible, well-structured prototype with a real end-to-end pipeline,
a distinctive interface, and an unusually honest evaluation posture for a
project of this size. Its strongest idea is the claim-level, contradiction-first
graph. Its weakest point is the evidence that the contradiction classifier is
correct at scale: four confirmed positives cannot carry a production precision
claim.

The next phase should not be "more features." It should be **more labels, better
measurement, and a human review loop**, followed by the operational hardening
needed to let anyone other than the author run it safely.

---

*Document version: 1.0 · Last verified 2026-10-24 · Maintained alongside the
code. If code and this brief disagree, re-verify the code and update both.*
