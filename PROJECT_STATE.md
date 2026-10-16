# PROJECT_STATE

> **Status:** supplementary reference. The authoritative, current project
> inventory is [`PROJECT_INFO.md`](PROJECT_INFO.md); actionable work is tracked
> in [`progress.md`](progress.md). Product name: **Axion**.

This document summarizes the current implementation status of Axion based on the repository’s actual source code and runtime wiring. It focuses on what is implemented now, what is partially implemented, and what is still missing or heuristic.

---

## Executive Summary

The repository is currently a working prototype of a graph-native scientific reasoning system. The core runtime path is implemented end to end:

- papers can be ingested from ArXiv,
- claims can be extracted and stored,
- contradictions and research gaps can be generated,
- a multi-agent query pipeline can synthesize cited reports,
- a FastAPI backend and a Next.js UI are both wired to the backend.

The implementation is substantial and functional, but it still relies heavily on live external services (Neo4j, ChromaDB, LLM providers) and several behaviors are heuristic rather than fully deterministic.

---

## Overall Status

### Fully implemented and active
- End-to-end ingestion pipeline
- Neo4j-backed claim and relationship persistence
- ChromaDB-backed semantic retrieval
- Multi-agent coordinator workflow for Q&A
- FastAPI API surface
- Frontend workspace with multiple operational views
- Logging, metrics, scheduler, and ingestion progress tracking

### Partially implemented or heuristic
- Contradiction evaluation
- Confidence propagation
- Gap discovery
- Experiment recommendation
- Temporal reasoning
- Citation weighting
- Test coverage and operational hardening

### Not implemented or still basic
- Authentication and authorization
- Production-grade task queueing and async background processing
- Full observability stack beyond in-memory metrics
- Stronger validation, schema enforcement, and data quality pipelines

---

## Subsystem Status

### 1. Ingestion pipeline: Implemented

Status: Implemented and wired end to end.

What exists now:
- ArXiv paper search and PDF download in [ingestion/arxiv_client.py](ingestion/arxiv_client.py)
- PDF text extraction and section splitting in [ingestion/pdf_parser.py](ingestion/pdf_parser.py)
- Paper processing and claim extraction in [agents/reader.py](agents/reader.py)
- Storage into Neo4j and ChromaDB in [graph/neo4j_queries.py](graph/neo4j_queries.py) and [embeddings/store.py](embeddings/store.py)
- Scheduled and manual ingestion control in [ingestion/scheduler.py](ingestion/scheduler.py)
- CLI entry point in [main.py](main.py)

Current limitations:
- The pipeline depends on successful network access to ArXiv and LLM providers.
- It is not a fully incremental or transaction-safe ingestion system.
- Failure handling is mostly per-paper/per-section rather than end-to-end rollback.

### 2. Reader agent: Implemented

Status: Implemented and actively used in ingestion.

What exists now:
- Structured claim extraction prompts and normalization in [agents/reader.py](agents/reader.py)
- Storage of paper metadata, claims, and provenance-like fields
- Base confidence stamping and embedding persistence

Current limitations:
- Claim quality is LLM-driven and heuristic.
- Extraction is not deterministic and depends on prompt quality and model behavior.

### 3. Graph persistence layer: Implemented

Status: Implemented and functional.

What exists now:
- Neo4j driver abstraction and generic query helpers in [graph/neo4j_client.py](graph/neo4j_client.py)
- Domain query helpers in [graph/neo4j_queries.py](graph/neo4j_queries.py)
- Schema initialization and indexes in [graph/neo4j_schema.py](graph/neo4j_schema.py)
- Migration and repair scripts (e.g., `migrate_to_neo4j.py`, `migrate_base_confidence.py`, `migrate_add_year.py`, `fix_gap_links.py`, `fix_empty_gap_links.py`, `fix_chroma_year_type.py`) for handling historical data issues in `graph/`
- Support for Paper, Claim, Gap, and relationship types such as EXTRACTED_FROM, CONTRADICTS, SUPPORTS, and RELATED_TO

Current limitations:
- The graph layer is functional but not yet a fully hardened data model with exhaustive validation.
- Some values are stored as plain strings or JSON strings rather than as strongly normalized graph properties.

### 4. Contradiction detection: Implemented

Status: Implemented and active.

What exists now:
- Similarity-based retrieval plus LLM judgment in [agents/contradiction.py](agents/contradiction.py)
- Relationship insertion into Neo4j through [graph/neo4j_queries.py](graph/neo4j_queries.py)
- Automatic confidence recalculation after detection runs in [agents/confidence_updater.py](agents/confidence_updater.py)

Current limitations:
- The logic is still heuristic and depends on semantic similarity plus an LLM decision step.
- It does not yet include a broad adversarial validation workflow beyond the basic contradiction/support/unrelated split.

### 5. Confidence propagation: Implemented

Status: Implemented and integrated.

What exists now:
- Recalculation logic in [agents/confidence_updater.py](agents/confidence_updater.py)
- Endpoint support in [api/main.py](api/main.py)
- UI integration in [axion/components/axion/graph-evolution.tsx](axion/components/axion/graph-evolution.tsx)

Current limitations:
- The formula is a simple heuristic based on support and contradiction counts.
- It does not yet incorporate richer paper quality, provenance, or citation semantics beyond the citation-based weighting helper in [agents/citation.py](agents/citation.py).

### 6. Gap finding: Implemented

Status: Implemented but still lightweight.

What exists now:
- Future-work and limitation extraction in [agents/gap_finder.py](agents/gap_finder.py)
- Gap insertion and linking to related claims in [graph/neo4j_queries.py](graph/neo4j_queries.py)
- API and UI exposure in [api/main.py](api/main.py) and [axion/components/axion/gap-list.tsx](axion/components/axion/gap-list.tsx)

Current limitations:
- Gaps are generated from LLM analysis and semantic neighborhood heuristics.
- The downstream use of gaps is present but still fairly shallow compared with the broader claim-reasoning system.

### 7. Experiment recommender: Implemented

Status: Implemented and stored in the graph.

What exists now:
- Experiment design generation in [agents/experiment_recommender.py](agents/experiment_recommender.py)
- Storage on contradiction relationships in Neo4j
- API endpoints and UI rendering hooks in [api/main.py](api/main.py) and [axion/components/axion/contradiction-list.tsx](axion/components/axion/contradiction-list.tsx)

Current limitations:
- Experiment generation depends on LLM output quality.
- It is not yet a fully automated part of every contradiction cycle unless explicitly triggered.

### 8. Coordinator / query pipeline: Implemented

Status: Implemented and central to the product experience.

What exists now:
- Planner, reflector, synthesizer, and coordinator orchestration in [agents/coordinator_v2.py](agents/coordinator_v2.py), [agents/planner.py](agents/planner.py), [agents/reflector.py](agents/reflector.py), and [agents/synthesizer.py](agents/synthesizer.py)
- Retrieval over ChromaDB and Neo4j-backed claims
- Reflection loop and report synthesis
- API endpoint in [api/main.py](api/main.py)
- Frontend query experience in [axion/components/axion/query-panel.tsx](axion/components/axion/query-panel.tsx)

Current limitations:
- All planning and synthesis behavior is still LLM-mediated.
- The workflow is not fully deterministic and is bounded by a small iteration loop rather than a deeper reasoning engine.

### 9. Temporal reasoning: Implemented

Status: Implemented as an auxiliary capability.

What exists now:
- Year-filtered claim retrieval, consensus evolution analysis, and contradiction timeline logic in [agents/temporal.py](agents/temporal.py)
- API endpoints in [api/main.py](api/main.py)
- UI support in [axion/components/axion/timeline-view.tsx](axion/components/axion/timeline-view.tsx)

Current limitations:
- Temporal output is generated from LLM interpretation of retrieved claims rather than from a strict formal temporal model.

### 10. Citation engine: Implemented

Status: Implemented but network-dependent.

What exists now:
- Semantic Scholar fetch and weighting in [agents/citation.py](agents/citation.py)
- Usage in coordinator retrieval confidence in [agents/coordinator_v2.py](agents/coordinator_v2.py)

Current limitations:
- It relies on external API availability and rate limits.
- The scoring is heuristic rather than a rigorous scholarly-quality measure.

### 11. FastAPI backend: Implemented

Status: Implemented and exposed.

What exists now:
- Main API app in [api/main.py](api/main.py)
- Pydantic models in [api/models.py](api/models.py)
- Endpoints for statistics, claims, contradictions, experiments, gaps, query execution, temporal analysis, confidence analysis, ingestion, graph data, health checks, and metrics

Current limitations:
- Some responses include placeholder or simplified values for fields such as graph node metadata and gap confidence.
- The backend assumes its dependent services are reachable at startup.

### 12. Frontend UI: Implemented

Status: Implemented as a multi-view workspace.

What exists now:
- Main app shell in [axion/app/page.tsx](axion/app/page.tsx)
- Query panel, knowledge graph view, contradictions view, gaps view, timeline view, evolution view, and ingestion panel in the Axion workspace

Current limitations:
- The UI is strongly dependent on the backend and live data.
- It appears to be a polished interface for a prototype rather than a fully hardened production application.

### 13. Testing: Present but mixed

Status: Partial coverage exists, but it is not comprehensive.

What exists now:
- Neo4j integration tests in [tests/test_neo4j.py](tests/test_neo4j.py)
- Agent and smoke-style tests in [tests/test_agents.py](tests/test_agents.py), [tests/test_phase4.py](tests/test_phase4.py), [tests/test_phase5.py](tests/test_phase5.py), and [tests/test_axion.py](tests/test_axion.py)

Current limitations:
- Many tests depend on live Neo4j or ChromaDB services.
- The suite does not appear to be a fully isolated unit-test suite for all major components.

### 14. Observability and operational utilities: Implemented

Status: Implemented in a lightweight form.

What exists now:
- Structured logging in [utils/logger.py](utils/logger.py)
- Metrics collection in [utils/metrics.py](utils/metrics.py)
- Ingestion progress tracking in [ingestion/progress.py](ingestion/progress.py)
- Backup utilities in [graph/backup.py](graph/backup.py)

Current limitations:
- Metrics are in-memory only.
- There is no dedicated monitoring, tracing, or alerting pipeline in place.

### 15. Authentication and security: Not implemented

Status: Not present in the current implementation.

What is missing:
- No user authentication layer
- No role-based access control
- No production-grade API security beyond simple header-based secret handling for ingestion triggers

### 16. Production hardening: Not yet reached

Status: Prototype-level operational maturity.

What is missing:
- A durable background task system
- Better deployment and environment management
- Stronger data validation and migration discipline
- More comprehensive automated regression coverage

### 17. Legacy code and interfaces: Archived or Removed

Status: Legacy SQLite paths and prototypes are no longer active.

What exists now:
- Older SQLite schema and queries have been moved to [archive/](archive/) (e.g., `graph_queries_sqlite.py`, `graph_schema_sqlite.py`, `coordinator_v1.py`).
- The legacy Streamlit UI (`ui/`) and older graph scripts (like `graph/queries.py`) have been entirely removed from the main branch, fully replaced by the Axion Next.js frontend and Neo4j backend.

---

## Current Implementation Maturity

The codebase is best described as a functional research-system prototype with a strong backend/core implementation and a polished frontend shell.

Most mature areas:
- ingestion and claim processing
- graph storage and retrieval
- coordinator-driven query synthesis
- API and UI integration

Least mature areas:
- authentication
- production deployment posture
- deterministic evaluation and testing
- reliability under service failures and large-scale ingestion

---

## Bottom Line

The repository currently contains a real, working implementation of a multi-agent scientific research system rather than a scaffold or mockup. The core idea is implemented and connected across ingestion, storage, reasoning, API, and UI layers. The remaining work is primarily about hardening, reliability, and making the system less dependent on live LLM and external-service behavior.
