# AI_CONTEXT

> **Status:** supplementary reference. The authoritative, current project
> inventory is [`PROJECT_INFO.md`](PROJECT_INFO.md); actionable work is tracked
> in [`progress.md`](progress.md). Product name: **Axion**.

## Project Overview

### What this project does
This repository implements a multi-agent scientific intelligence system for ingesting research papers, extracting atomic empirical claims, storing them in a knowledge graph, detecting contradictions and supports between claims, finding research gaps, and synthesizing cited research reports for user questions.

The codebase is a hybrid of:
- a Python backend that orchestrates ingestion, graph operations, LLM reasoning, and API endpoints
- a Next.js/TypeScript frontend workspace called Axion for browsing the knowledge graph and querying the system

### Main goal
The primary goal is not simple document search. The system is meant to reason over scientific literature at the claim level so that it can answer questions such as:
- which findings are agreed upon
- which findings conflict
- which areas remain unexplored
- what experiment would resolve a dispute

### Core workflow
The repository follows a pipeline with three major modes:
1. Ingest papers from arXiv
2. Parse and extract claims into a graph and vector store
3. Use agents to reason over those claims and answer user questions

### Main technologies
- Python 3.10+
- FastAPI for the backend API
- Neo4j for the property graph database
- ChromaDB for vector similarity search
- Sentence Transformers / all-MiniLM-L6-v2 for embeddings
- LLM providers through a unified wrapper: Groq, Gemini, Claude
- Next.js and TypeScript for the Axion frontend
- PyMuPDF for PDF extraction
- APScheduler for background ingestion

### High-level architecture
The repository uses a layered architecture:

```text
User / Browser / CLI
        ↓
   FastAPI API
        ↓
Coordinator + specialized agents
        ↓
Neo4j graph + ChromaDB vectors + LLM providers
        ↓
Structured report / dashboard / graph UI
```

The system is graph-native: scientific evidence is stored as nodes and relationships rather than as plain document chunks.

---

## Complete Data Flow

### 1. Ingestion flow
```text
ArXiv search query
    ↓
arxiv_client.search_papers()
    ↓
download_pdf()
    ↓
pdf_parser.extract_text() / extract_sections()
    ↓
reader.process_paper()
    ↓
LLM extracts structured claims
    ↓
Neo4j: create Paper + Claim nodes and EXTRACTED_FROM edges
    ↓
ChromaDB: embed claim text and store with metadata
    ↓
contradiction detection compares new claims to similar claims
    ↓
confidence_updater recalculates claim confidence
    ↓
optional gap finding and experiment recommendation
```

### 2. Query flow
```text
User asks a question in the UI or via CLI/API
    ↓
FastAPI /api/query
    ↓
Coordinator v2
    ├─ Planner creates sub-queries
    ├─ Retriever searches ChromaDB and Neo4j
    ├─ Reflector judges whether context is sufficient
    └─ Synthesizer writes a report
    ↓
LLM produces a structured answer with citations
    ↓
Frontend renders report, citations, contradictions, gaps, and timeline
```

### 3. Full journey from user input to output
```text
User
↓
Next.js frontend or CLI
↓
FastAPI endpoint
↓
Coordinator v2
↓
Planner → Retriever → Reflector → Synthesizer
↓
Neo4j + ChromaDB retrieval
↓
LLM response generation
↓
Structured markdown report / JSON payload
↓
Frontend display
```

---

## Folder Responsibilities

### agents/
Purpose:
The reasoning layer of the system. These modules encapsulate domain-specific agent behavior.

What belongs here:
- reader.py: paper parsing and claim extraction
- contradiction.py: contradiction/support detection between claims
- confidence_updater.py: confidence propagation based on graph topology
- gap_finder.py: research gap mining from future-work text and clusters
- experiment_recommender.py: proposes experiments to resolve contradictions
- coordinator_v2.py: orchestrates planning, retrieval, reflection, and synthesis
- planner.py, reflector.py, synthesizer.py: sub-steps of the query pipeline
- temporal.py: temporal and trend analysis
- citation.py: citation count retrieval and weighting

What must never belong here:
- direct database connection boilerplate that should live in graph/
- HTTP route handlers; those belong in api/
- frontend UI React components
- low-level embedding persistence logic; that belongs in embeddings/

### api/
Purpose:
HTTP API surface for the backend.

What belongs here:
- FastAPI app setup
- route handlers for stats, claims, contradictions, experiments, gaps, query, temporal, confidence, ingestion, and graph data
- Pydantic response models

What must never belong here:
- LLM business logic or agent orchestration details beyond HTTP adaptation
- raw Neo4j query implementation
- frontend rendering logic

### graph/
Purpose:
The persistence and query abstraction layer for Neo4j.

What belongs here:
- neo4j_client.py: Neo4j driver singleton and generic query execution helpers
- neo4j_queries.py: domain-specific Cypher helpers for papers, claims, relationships, gaps, and stats
- neo4j_schema.py: schema initialization and index creation
- backup.py: Neo4j backup utilities
- migration scripts and repair scripts for historical data issues

What must never belong here:
- LLM prompt definitions
- React components
- PDF text extraction
- business rules for contradiction detection

### embeddings/
Purpose:
Vector storage and semantic retrieval.

What belongs here:
- ChromaDB client access
- embedding creation and upsert logic
- similarity search over claims and paper chunks

What must never belong here:
- Neo4j graph schema design
- API routes
- agent reasoning prompts

### ingestion/
Purpose:
All ingestion and scheduling logic for bringing new papers into the system.

What belongs here:
- arxiv_client.py: arXiv search and PDF download
- pdf_parser.py: PDF text extraction and section splitting
- scheduler.py: recurring ingestion jobs
- progress.py: progress tracking for custom ingestion runs

What must never belong here:
- graph schema definitions
- frontend UI code
- final answering/report writing

### axion/ (frontend)
Purpose:
The user-facing workspace UI.

What belongs here:
- Next.js pages and app shell
- components for query, graph, contradictions, gaps, timeline, and ingestion
- TypeScript API client and shared types

What must never belong here:
- core business logic for claim extraction or contradiction detection
- direct database access or Cypher
- LLM prompts

### tests/
Purpose:
Regression and integration coverage for the repository.

What belongs here:
- unit tests for agents and parsing helpers
- integration tests for Neo4j and the graph layer
- smoke tests for major features and regressions

What must never belong here:
- production logic or business implementations
- manual data fixtures intended to be used in production

### utils/
Purpose:
Cross-cutting support modules.

What belongs here:
- logger.py: logging and tracing helpers
- llm_parser.py: robust JSON and claim normalization
- llm_cache.py: in-process LLM call caching
- metrics.py: in-memory metrics collector
- ingestion_report.py: ingestion summary formatting

What must never belong here:
- model-specific business rules
- graph domain logic that should be in graph/
- frontend presentation code

### Legacy code (removed 2026-10-24)
The old SQLite prototype and the superseded 2026-10-21 ablation copy were deleted.
Recover them from git history if needed; do not add new legacy code to the active
tree.

---

## Layered Architecture

### Frontend
The frontend is a Next.js + TypeScript experience that provides:
- a research query workspace
- graph visualization of papers/claims/gaps
- contradiction browsing
- timeline and confidence evolution views
- ingestion controls

It communicates with the backend through the FastAPI API.

### API
The API layer is thin and adapter-like:
- validates incoming requests
- delegates work to agents or graph modules
- returns structured JSON or markdown output

It does not contain deep reasoning logic; it mainly coordinates.

### Services
The service layer is effectively the Python agent system:
- ingest pipeline
- contradiction engine
- confidence updater
- gap finder
- experiment recommender
- coordinator loop

These modules encapsulate the repository’s core intellectual behavior.

### Agents
Each agent has a single responsibility:
- Reader extracts claims
- Contradiction agent detects relationships
- Confidence updater propagates trust signals
- Gap finder mines unanswered questions
- Experiment recommender proposes tests
- Planner/Reflector/Synthesizer form the query-answering loop

### Database
The repository uses:
- Neo4j for structured knowledge and relationships
- ChromaDB for semantic similarity search

### Embeddings
Embeddings are created from claim text and paper chunks and stored in ChromaDB. Similarity search is used to retrieve semantically related claims for contradiction detection and question answering.

### LLM
The LLM layer is centralized in llm.py and is abstracted behind a single function, call_llm(). All agents use this interface instead of calling providers directly.

### Utilities
Utilities provide generic support for logging, parsing, caching, metrics, and formatting. They are shared across agents and API layers.

---

## Global Coding Rules

### Naming conventions
- Python modules and functions use snake_case.
- Python classes use PascalCase where needed.
- Neo4j labels and relationship types are uppercase (Paper, Claim, Gap, CONTRADICTS, SUPPORTS, RELATED_TO).
- React/TypeScript code uses camelCase and PascalCase for components.

### Logging
- Logging is centralized through utils.logger.get_logger() and log_event().
- Agents commonly use trace_agent() decorators to log start/complete/failure timing.
- The system supports either text or JSON log formatting via environment variables.

### Typing
- Python modules use type hints where practical.
- Pydantic models define API request/response shapes in api/models.py.
- TypeScript interfaces mirror the backend API responses in axion/types/axion.ts.

### Error handling
- The repository prefers defensive, fault-tolerant behavior over crashing.
- claim extraction and gap finding tolerate malformed LLM output via robust parsers.
- per-section and per-paper failures are isolated so one failed section does not kill the whole paper.
- API routes return structured HTTP errors rather than uncaught exceptions.

### Configuration
- Configuration is centralized in config.py.
- Environment variables are loaded through python-dotenv.
- LLM provider selection, Neo4j connection settings, scheduler intervals, allowed origins, and file paths all come from configuration.

### Dependency injection
There is no formal dependency-injection framework. The repository uses:
- shared singletons for the Neo4j driver and metrics collector
- module-level helper functions and imported utilities
- explicit function parameters for important dependencies

### Import patterns
- Modules tend to import from sibling packages directly.
- Heavy dependencies are often imported lazily so tests and lightweight imports remain fast.
- Embeddings store intentionally avoids eager loading of ChromaDB and model weights at import time.

---

## Database

### Neo4j
Neo4j is the primary knowledge store.

What it stores:
- Paper nodes with arxiv_id, title, authors, abstract, published year, citation count
- Claim nodes with text, confidence, section, provenance fields, paper year, structured metadata
- Gap nodes with generated research questions and source metadata
- Relationships:
  - EXTRACTED_FROM: paper → claim
  - CONTRADICTS: claim → claim
  - SUPPORTS: claim → claim
  - RELATED_TO: gap → claim

Why it is used:
- the system needs graph traversal and relationship-based reasoning
- contradictions and gaps are fundamentally graph facts

### ChromaDB
ChromaDB stores vector embeddings for semantic retrieval.

What it stores:
- embeddings for paper chunks
- embeddings for claims
- metadata such as arxiv_id, section, paper_year, claim_id

Why it is used:
- the coordinator and contradiction engine need semantic nearest-neighbor search
- it is a fast retrieval layer over texts and claims

### SQLite
The active runtime code does not use SQLite for production logic. The legacy SQLite scripts were removed on 2026-10-24 (recoverable from git history), and `config.py` still exposes a legacy `DB_PATH`; the current implementation is graph-first and uses Neo4j plus ChromaDB.

---

## LLM Architecture

### How LLMs are called
All LLM access is routed through llm.py via call_llm().

That wrapper:
- accepts a prompt and token budget
- selects a provider
- retries on rate-limits with exponential backoff and jitter
- optionally uses an in-process cache
- returns a normalized response string

### Where prompts exist
Prompts are stored as module-level strings near the relevant agent implementation:
- agents/reader.py: claim extraction prompt
- agents/contradiction.py: contradiction/support prompt
- agents/gap_finder.py: gap extraction prompts
- agents/planner.py: planning prompt
- agents/reflector.py: reflection prompt
- agents/synthesizer.py: synthesis prompt
- agents/experiment_recommender.py: experiment design prompt
- agents/temporal.py: temporal analysis prompts

### How models are selected
Model names and provider settings are defined in config.py:
- LLM_PROVIDER selects the primary provider
- LLM_PROVIDER_CHAIN defines fallback order
- provider-specific model names are defined per provider

### How providers are abstracted
The abstraction lives in llm.py:
- _call_groq()
- _call_gemini()
- _call_claude()

Agents never call the providers directly. They call call_llm() and the router handles the backend details.

---

## Complete Request Lifecycle

### HTTP request path
1. The user submits a question in the Axion frontend.
2. The frontend sends a POST request to /api/query.
3. FastAPI validates the request body.
4. The API delegates to agents.coordinator_v2.run().
5. The coordinator runs planning, retrieval, reflection, and synthesis.
6. Neo4j and ChromaDB provide the context.
7. The LLM generates a structured synthesis.
8. The FastAPI route returns the report JSON and metadata to the UI.
9. The UI renders the report, citations, and reasoning trace.

### Ingestion request lifecycle
1. A CLI command or API trigger starts ingestion.
2. arxiv_client searches arXiv for papers.
3. PDFs are downloaded.
4. pdf_parser extracts text and sections.
5. reader.process_paper() extracts claims.
6. claims are written to Neo4j and ChromaDB.
7. contradiction detection runs over similar claims.
8. confidence is recalculated.
9. optional gap finding and experiment recommendation may run.

### Graph write lifecycle
Any write to the graph goes through:
- graph.neo4j_client.run_write()
- or graph.neo4j_queries helper functions that wrap run_write()

This keeps Cypher logic centralized and consistent.

---

## Repository Philosophy

The repository is built around a few clear engineering principles:

- Graph-native reasoning over flat document retrieval
- Evidence-first synthesis backed by explicit relationships
- Defensiveness over brittleness: parsers tolerate malformed outputs
- Modularity: separate agents for planning, retrieval, reflection, synthesis, contradiction detection, and gap mining
- Explicit uncertainty: confidence scores and structured reasoning are first-class artifacts
- Local-first operation: the system can run with local embeddings and a local Neo4j instance, with external LLM providers as optional inference backends
- Incremental evolution: the codebase has explicit migration and repair scripts rather than assuming a perfect initial schema

In short, this is a research infrastructure system, not a simple chatbot wrapper. Its core design is to turn scientific literature into a navigable, connected body of evidence and to support reasoning over that evidence.
