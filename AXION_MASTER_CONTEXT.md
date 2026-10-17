# AXION MASTER CONTEXT

> **Status:** supplementary reference. The authoritative, current project
> inventory is [`PROJECT_INFO.md`](PROJECT_INFO.md); actionable work is tracked
> in [`progress.md`](progress.md). Product name: **Axion**.

## Purpose

This document is the technical single source of truth for the Axion repository. It is intended for a future developer who returns after months away and needs to understand how the system works without reading the entire codebase from scratch.

This document is implementation-driven. Where the code and earlier notes diverge, the code is treated as the source of truth.

---

## 1. Project Identity

This repository implements a graph-native scientific intelligence system that:

- ingests research papers from arXiv,
- extracts atomic, falsifiable claims from paper sections,
- stores those claims in a Neo4j knowledge graph,
- embeds claims in ChromaDB for semantic retrieval,
- detects contradictions and supports between claims,
- recalculates claim confidence based on graph relationships,
- discovers research gaps,
- recommends experiments to resolve disputes, and
- answers user questions through a multi-agent reasoning pipeline.

The system is not just a document search tool. Its central abstraction is the claim, and its core value comes from understanding relationships between claims across papers.

---

## 2. Core Mental Model

The best way to reason about this project is as a layered system:

1. Ingestion layer
   - fetches papers,
   - parses PDFs,
   - extracts sections,
   - turns sections into structured claims.

2. Persistence layer
   - stores papers and claims in Neo4j,
   - stores embeddings and text chunks in ChromaDB.

3. Intelligence layer
   - compares claims,
   - detects contradictions/supports,
   - recalculates confidence,
   - finds gaps,
   - designs experiments.

4. Query / reasoning layer
   - plans a research question,
   - retrieves relevant claims from the graph and vector store,
   - reflects on whether enough context exists,
   - synthesizes a report.

5. Experience layer
   - exposes the workload through a FastAPI backend,
   - renders dashboards and panels through a Next.js / TypeScript frontend named Axion.

The project is therefore a hybrid of:
- Python orchestration and agent logic,
- graph persistence,
- vector retrieval,
- LLM-assisted reasoning,
- and a web UI.

---

## 3. Repository Structure

Key top-level areas:

- main.py
  - CLI entry point for ingestion, contradiction detection, gaps, query, confidence recalculation, experiments, and scheduler control.

- llm.py
  - unified LLM router with provider fallback, retries, rate-limit handling, caching, and metrics hooks.

- config.py
  - environment-driven configuration for models, providers, Neo4j, ChromaDB, scheduler, and API settings.

- agents/
  - reasoning agents for reading, contradiction detection, confidence updates, gap detection, experiments, planning, reflection, synthesis, temporal reasoning, and citations.

- graph/
  - Neo4j driver abstraction, graph-domain Cypher helpers, schema initialization, backups, and migrations.

- embeddings/
  - ChromaDB interface for claims and paper chunk embeddings.

- ingestion/
  - arXiv search, PDF download, PDF parsing, scheduler, and progress tracking.

- api/
  - FastAPI application and request/response models.

- axion/
  - Next.js / TypeScript frontend workspace.

- utils/
  - shared utilities such as logging, LLM parsing, metrics, and ingestion reporting.

- tests/
  - regression and integration tests.

---

## 4. Runtime Configuration

Configuration is centralized in config.py and loaded from environment variables via python-dotenv.

### 4.1 LLM configuration

The system supports:
- Groq,
- Gemini,
- Claude.

The following settings are important:
- LLM_PROVIDER
- LLM_PROVIDER_CHAIN
- LLM_CACHE_ENABLED
- GROQ_API_KEY / GEMINI_API_KEY / ANTHROPIC_API_KEY
- GROQ_MODEL / GEMINI_MODEL / CLAUDE_MODEL

The default provider chain is:
- primary: groq
- fallback: groq → gemini

### 4.2 Storage configuration

Relevant storage settings:
- NEO4J_URI
- NEO4J_USER / NEO4J_PASSWORD
- CHROMA_DIR
- EMBEDDING_MODEL
- DATA_DIR / DB_PATH / PAPERS_DIR

### 4.3 Scheduler configuration

The scheduler uses:
- SCHEDULER_INTERVAL_HOURS
- SCHEDULER_PAPERS_PER_RUN
- SCHEDULER_TOPICS

### 4.4 Other runtime settings

- MAX_CLAIMS_PER_PAPER
- CONTRADICTION_THRESHOLD
- ALLOWED_ORIGINS
- AXION_API_KEY        (write/compute endpoint auth; X-API-Key header)
- AXION_API_URL        (backend address for the Next.js server-side proxy)
- TRIGGER_SECRET       (legacy alias for ingestion triggers)

---

## 5. Core Execution Paths

### 5.1 Ingestion path

The main ingestion path is:

1. search_papers(query, max_results=N) in ingestion/arxiv_client.py
2. download_pdf(arxiv_id) in ingestion/arxiv_client.py
3. extract_sections(pdf_path) in ingestion/pdf_parser.py
4. process_paper(paper_meta, pdf_path) in agents/reader.py
5. insert_paper(...) and insert_claim(...) in graph/neo4j_queries.py
6. add_chunk(...) / add_claim(...) in embeddings/store.py
7. optional contradiction detection and confidence recalculation

The reader agent:
- extracts sections like Abstract, Introduction, Results, Experiments, Conclusion, and preamble,
- calls the LLM to extract structured claims,
- stores those claims in Neo4j and vector store,
- persists provenance-like fields such as evidence span and structured metadata when available.

### 5.2 Contradiction path

The contradiction pipeline is:

1. get_all_claims() reads claim nodes from Neo4j.
2. find_similar_claims(...) retrieves semantically similar claims from ChromaDB.
3. check_pair(...) sends a prompt to the LLM to classify the pair as CONTRADICTS / SUPPORTS / UNRELATED.
4. insert_relationship(...) writes the relationship into the graph.
5. recalculate_all() updates claim confidence in Neo4j.

The contradiction agent is intentionally conservative and uses semantic similarity as a prefilter. Not every similar pair is a true contradiction.

### 5.3 Confidence path

Claim confidence is not static. After new relationships are created, the confidence updater recalculates each claim using a simple graph-based heuristic:

Confidence = base_confidence + (0.08 × supports) - (0.12 × contradictions)

The value is clamped to [0.05, 0.98].

This module is central to the system’s self-correction behavior.

### 5.4 Gap-finding path

Gap finding currently works in two modes:
- future work / limitations mining from paper sections,
- cluster-based gap generation from semantically related claims.

The results are stored as Gap nodes with RELATED_TO edges to claims.

### 5.5 Experiment recommendation path

For each contradiction, the experiment recommender can design a targeted experiment to resolve the dispute. The design is stored as JSON on the CONTRADICTS relationship in Neo4j.

### 5.6 Query / synthesis path

The main query pipeline is coordinator_v2.py. It follows a Plan → Retrieve → Reflect → Synthesize loop:

1. Planner creates sub-queries.
2. Retriever searches ChromaDB for relevant claims and Neo4j for related contradictions and gaps.
3. Reflector scores whether the context is sufficient; if not, it refines the query.
4. Synthesizer writes a cited research report.

The loop is capped at three iterations.

---

## 6. The Most Important Modules

### 6.1 main.py

Entry point for CLI usage. Supports modes such as:
- ingest
- contradict
- gaps
- query
- backup
- schedule
- citations
- confidence
- experiments

This file wires the CLI to the agent modules and initialization routines.

### 6.2 llm.py

The LLM layer is intentionally centralized. It provides:
- unified provider calls,
- fallback across providers,
- retry and backoff on rate limits,
- optional caching,
- basic metrics integration.

All major agent modules should go through this layer rather than calling provider SDKs directly.

### 6.3 agents/reader.py

This is the ingestion agent.

Responsibilities:
- parse PDFs into section text,
- call the LLM to extract claims,
- normalize outputs with the parser utility,
- insert claims into Neo4j,
- store claim and chunk embeddings in ChromaDB.

It is the most critical pipeline for populating the graph.

### 6.4 agents/contradiction.py

Responsible for building relationship edges between claims. It uses semantic similarity to identify candidate pairs, then uses LLM judgment to decide whether the relationship is:
- CONTRADICTS,
- SUPPORTS,
- or UNRELATED.

### 6.5 agents/confidence_updater.py

This module updates claim confidence based on the graph topology. It is called after contradiction detection and after scheduled ingestion runs.

### 6.6 agents/coordinator_v2.py

This is the main orchestration layer for user-facing research questions.

It combines:
- planner.py,
- reflector.py,
- synthesizer.py,
- temporal.py,
- citation.py,
- ChromaDB retrieval,
- Neo4j retrieval.

### 6.7 graph/neo4j_queries.py

This file is the graph-domain abstraction layer.

It contains functions for:
- inserting and retrieving papers,
- inserting and retrieving claims,
- creating relationships,
- retrieving contradictions and supports,
- creating gaps,
- retrieving graph stats.

Anything involving graph structure should go through this layer rather than being written inline in other modules.

### 6.8 embeddings/store.py

This file wraps ChromaDB.

Responsibility areas:
- create or get collections,
- upsert chunk and claim embeddings,
- query for similar claims and chunks,
- expose collection stats for health checks.

### 6.9 api/main.py

The FastAPI backend exposes endpoints for:
- stats,
- claims,
- contradictions,
- experiments,
- research gaps,
- query synthesis,
- temporal evolution,
- disputes,
- confidence distribution,
- most-changed claims,
- ingestion status and triggers,
- graph data,
- health checks,
- metrics.

The UI depends on these endpoints heavily.

### 6.10 axion components

The frontend uses multiple panels to visualize the knowledge graph, contradictions, gaps, timeline, and ingestion pipeline. The main components are:
- query-panel.tsx
- knowledge-graph.tsx
- contradiction-list.tsx
- gap-list.tsx
- timeline-view.tsx
- graph-evolution.tsx
- ingestion-status.tsx

---

## 7. Data Model Basics

### 7.1 Paper nodes

Paper nodes store:
- arxiv_id
- title
- authors
- abstract
- published
- year

### 7.2 Claim nodes

Claim nodes store:
- text
- section
- confidence
- base_confidence
- paper_year
- subject / predicate / object_val / metric / direction
- evidence_span
- conditions
- embedding_id
- support_count / contradiction_count

Each claim is linked to a paper with an EXTRACTED_FROM edge.

### 7.3 Relationship edges

The graph uses:
- CONTRADICTS
- SUPPORTS
- RELATED_TO
- EXTRACTED_FROM

### 7.4 Gap nodes

Gap nodes store:
- text
- source

They are linked to claims via RELATED_TO edges.

---

## 8. The Graph and Vector Store Are Complementary

This is an important architectural distinction.

- Neo4j is the authoritative, relational graph for structured knowledge and relationships.
- ChromaDB is the retrieval layer for semantic similarity and contextual search.

The system uses both together:
- ChromaDB helps find nearby claims semantically.
- Neo4j stores the actual graph logic and relationship structure.

The developer should not assume that one replaces the other.

---

## 9. Key Design Constraints and Tradeoffs

### 9.1 The confidence model is heuristic

The current confidence formula is simple and explainable, but not a rigorous probabilistic model. It is meant to create a useful signal, not a perfect scientific measure.

### 9.2 Contradiction detection is LLM-assisted

The contradiction engine uses vector retrieval to narrow candidate comparisons, then relies on the LLM to judge logical relation. That means it can still produce false positives when the scope of the claims differs.

### 9.3 The system relies on external services

The runtime depends on:
- Neo4j,
- ChromaDB,
- and LLM provider APIs.

If any of those are unavailable, the system will degrade or fail in predictable ways.

### 9.4 The ingestion pipeline is not fully asynchronous

Ingestion is mostly synchronous in the current implementation. The scheduler and progress tracker help, but this is still a prototype-scale pipeline rather than a high-throughput production pipeline.

---

## 10. Known Operational Notes

### 10.1 Local startup expectations

The backend expects Neo4j and ChromaDB to be available. If either is not reachable, the API startup checks will fail.

### 10.2 The UI assumes the API is running

The Next.js frontend calls the Python backend over HTTP. The API must be up before the frontend will behave normally.

### 10.3 The system is data-dependent

The quality of the system output depends heavily on the quality and volume of ingested papers and extracted claims. A sparse graph leads to weak query results.

### 10.4 The scheduler is background-based

The scheduler uses APScheduler and can run ingestion jobs at a configured interval.

---

## 11. How to Understand the Project Quickly

If a new developer needs to orient quickly, the best order is:

1. read main.py to see CLI entry points,
2. read llm.py to understand the central LLM abstraction,
3. read config.py to understand runtime configuration,
4. read agents/reader.py to understand ingestion,
5. read agents/contradiction.py and agents/confidence_updater.py to understand graph enrichment,
6. read agents/coordinator_v2.py to understand the user-facing reasoning flow,
7. read api/main.py and the Axion components to understand the frontend/backend contract,
8. read graph/neo4j_queries.py and embeddings/store.py to understand persistence abstractions.

That sequence will provide the shortest path to a working mental model.

---

## 12. Practical Commands

### Backend CLI

- Ingest papers:
  - python main.py --mode ingest --query "..." --n 10

- Run contradiction detection:
  - python main.py --mode contradict

- Run gap finding:
  - python main.py --mode gaps

- Run query pipeline:
  - python main.py --mode query --query "..."

- Recalculate confidence:
  - python main.py --mode confidence

- Design experiments:
  - python main.py --mode experiments

### API

- Start API:
  - uvicorn api.main:app --reload --port 8000

### Frontend

- Start Axion:
  - cd axion && pnpm install && pnpm dev

---

## 13. Summary

The repository is a prototype scientific reasoning platform built around a claim-centric knowledge graph. Its core strength is not generic document retrieval, but the combination of:

- structured claim extraction,
- graph-based relationship modeling,
- semantic retrieval,
- LLM-based reasoning,
- and iterative synthesis over that graph.

The system’s real value appears when papers accumulate and the graph becomes richer. Once enough claims and relationships exist, the engine becomes much more than a search tool: it becomes a reasoning substrate over scientific literature.
