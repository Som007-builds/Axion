# FILE_MAP

> **Status:** supplementary reference. The authoritative, current project
> inventory is [`PROJECT_INFO.md`](PROJECT_INFO.md); actionable work is tracked
> in [`progress.md`](progress.md). Product name: **Axion**.

This document is a repository-wide map of the most important source files in Axion, grouped by responsibility and dependency flow. It is intended as a navigation aid for future debugging, extension, and onboarding work.

---

## 1. Repository at a Glance

The project is a hybrid system with:
- a Python backend for ingestion, graph persistence, agent reasoning, and API endpoints
- a Next.js/TypeScript frontend workspace under [axion](axion)
- Neo4j + ChromaDB as the core storage stack
- a multi-agent pipeline for extracting claims, detecting contradictions, finding gaps, and answering questions

### Primary execution paths
- Ingestion path: [main.py](main.py) -> [ingestion/arxiv_client.py](ingestion/arxiv_client.py) -> [ingestion/pdf_parser.py](ingestion/pdf_parser.py) -> [agents/reader.py](agents/reader.py) -> [graph/neo4j_queries.py](graph/neo4j_queries.py) + [embeddings/store.py](embeddings/store.py)
- Query path: [api/main.py](api/main.py) -> [agents/coordinator_v2.py](agents/coordinator_v2.py) -> [agents/planner.py](agents/planner.py), [agents/reflector.py](agents/reflector.py), [agents/synthesizer.py](agents/synthesizer.py) -> [embeddings/store.py](embeddings/store.py) + [graph/neo4j_queries.py](graph/neo4j_queries.py)
- Contradiction path: [agents/contradiction.py](agents/contradiction.py) -> [embeddings/store.py](embeddings/store.py) -> [graph/neo4j_queries.py](graph/neo4j_queries.py) -> [agents/confidence_updater.py](agents/confidence_updater.py)

---

## 2. Root-Level Files

### [README.md](README.md)
- Project overview, architecture summary, setup instructions, and high-level capability description.
- Best entry point for understanding the product intent.

### [AI_CONTEXT.md](AI_CONTEXT.md)
- Repository-wide context document for another AI agent or future maintainer.
- Summarizes architecture, workflow, and key modules at a glance.

### [AXION_SPEC.md](AXION_SPEC.md)
- Engineering specification for the system.
- Useful when validating whether a change aligns with the intended architecture.

### [main.py](main.py)
- CLI entry point for running ingestion, contradiction detection, gap finding, query execution, backup, scheduling, and confidence recalculation.
- Important for local/manual pipeline operations.

### [config.py](config.py)
- Central configuration for provider selection, Neo4j, ChromaDB, embeddings, scheduler settings, and secrets.
- Every backend module depends on it indirectly or directly.

### [llm.py](llm.py)
- Unified LLM provider router with provider fallback, retries, caching, and metrics hooks.
- All agent modules that need LLM calls go through this layer.

### [requirements.txt](requirements.txt)
- Python dependency list for the backend.

### [docker-compose.yml](docker-compose.yml)
- Neo4j container configuration for local development.

### [pytest.ini](pytest.ini)
- Pytest configuration and marker settings.

---

## 3. Backend Core Modules

### [api/main.py](api/main.py)
- FastAPI application entry point.
- Exposes endpoints for stats, claims, contradictions, experiments, gaps, query execution, temporal analysis, confidence analysis, ingestion controls, graph data, health, and metrics.
- Main bridge between the frontend and the reasoning engine.

### [api/models.py](api/models.py)
- Pydantic response models used by the FastAPI routes.
- Keeps route payloads structured and frontend-aligned.

---

## 4. Agent Layer

### [agents/reader.py](agents/reader.py)
- Reader agent for paper ingestion.
- Extracts sections from PDF text, sends them to the LLM, normalizes claim output, and stores claims into Neo4j and ChromaDB.
- Core file for the ingestion pipeline.

### [agents/contradiction.py](agents/contradiction.py)
- Identifies contradictions and support relationships between claims.
- Uses semantic similarity plus an LLM judgment step.
- Writes relationships into the graph and triggers confidence recalculation.

### [agents/confidence_updater.py](agents/confidence_updater.py)
- Recomputes claim confidence as graph relationships accumulate.
- Implements the current confidence propagation logic.
- Used by the UI’s confidence evolution panel and backend endpoints.

### [agents/gap_finder.py](agents/gap_finder.py)
- Extracts open research questions from “future work” or limitation sections and from claim clusters.
- Writes gaps into Neo4j as Gap nodes with related-claim links.

### [agents/experiment_recommender.py](agents/experiment_recommender.py)
- Designs minimal experiments for high-confidence contradictions.
- Stores experiment designs on the contradiction relationship in Neo4j.

### [agents/coordinator_v2.py](agents/coordinator_v2.py)
- Main orchestrator for answering user questions.
- Implements a ReAct-style loop: plan -> retrieve -> reflect -> synthesize.
- The central agentic workflow for the question-answering experience.

### [agents/planner.py](agents/planner.py)
- Turns a user question into a retrieval plan.
- Produces sub-queries and decides whether contradictions/gaps are relevant.

### [agents/reflector.py](agents/reflector.py)
- Evaluates whether the retrieved context is sufficient.
- If not, it proposes a refined query for another retrieval round.

### [agents/synthesizer.py](agents/synthesizer.py)
- Converts retrieved context into a structured research report.
- Produces consensus, disputed points, gaps, recommendations, and confidence metadata.

### [agents/temporal.py](agents/temporal.py)
- Temporal reasoning helpers for trend analysis and dispute timelines.
- Supports year-filtered claim retrieval and evolution narratives.

### [agents/citation.py](agents/citation.py)
- Fetches citation counts from Semantic Scholar and applies citation-based weighting to claim confidence.
- Supports the citation-aware confidence heuristic.

---

## 5. Graph Layer

### [graph/neo4j_client.py](graph/neo4j_client.py)
- Low-level Neo4j driver singleton and generic query helpers.
- Central place to create sessions and run read/write Cypher operations.

### [graph/neo4j_queries.py](graph/neo4j_queries.py)
- Domain-specific Cypher helpers for papers, claims, relationships, gaps, and graph stats.
- This is the primary persistence abstraction used by the backend and agents.

### [graph/neo4j_schema.py](graph/neo4j_schema.py)
- Initial schema bootstrap for constraints and indexes.
- Critical for reliable graph behavior and query performance.

### [graph/backup.py](graph/backup.py)
- Utility for creating Neo4j backups via Docker and neo4j-admin.

### Migration and repair scripts
- [graph/migrate_to_neo4j.py](graph/migrate_to_neo4j.py): SQLite-to-Neo4j migration.
- [graph/migrate_add_year.py](graph/migrate_add_year.py): backfills paper year metadata.
- [graph/migrate_base_confidence.py](graph/migrate_base_confidence.py): backfills base confidence values.
- [graph/fix_chroma_year_type.py](graph/fix_chroma_year_type.py): converts Chroma metadata types.
- [graph/fix_gap_links.py](graph/fix_gap_links.py): repairs gap-to-claim link data.
- [graph/fix_empty_gap_links.py](graph/fix_empty_gap_links.py): links gaps to similar claims when missing.

---

## 6. Embeddings and Vector Store

### [embeddings/store.py](embeddings/store.py)
- ChromaDB wrapper for storing and querying embedding vectors.
- Used for semantic similarity retrieval of claims and paper chunks.
- Important dependency for retrieval and contradiction detection.

---

## 7. Ingestion Layer

### [ingestion/arxiv_client.py](ingestion/arxiv_client.py)
- Searches ArXiv for papers matching a topic and downloads PDFs.
- Main upstream data source for the ingestion pipeline.

### [ingestion/pdf_parser.py](ingestion/pdf_parser.py)
- Extracts readable text from PDFs and splits it into sections/chunks.
- Supplies the text that the reader agent uses to extract claims.

### [ingestion/scheduler.py](ingestion/scheduler.py)
- Background scheduler for recurring ingestion jobs.
- Supports periodic ingestion and custom ingestion runs.

### [ingestion/progress.py](ingestion/progress.py)
- Tracks progress for custom ingestion runs and exposes status for the UI.
- Used by the ingestion sheet in the frontend.

---

## 8. Utility Modules

### [utils/logger.py](utils/logger.py)
- Shared logging and tracing helpers.
- Provides structured logging and agent trace decorators.

### [utils/llm_parser.py](utils/llm_parser.py)
- Robust parser for LLM JSON output.
- Normalizes messy model outputs and validates claims.

### [utils/llm_cache.py](utils/llm_cache.py)
- In-process LLM response cache to reduce duplicate calls.

### [utils/metrics.py](utils/metrics.py)
- Lightweight in-memory metrics collector for LLM, graph, and ingestion events.

### [utils/ingestion_report.py](utils/ingestion_report.py)
- Terminal-friendly formatter for ingestion summary output.

---

## 9. Frontend Workspace: Axion

### [axion/app/page.tsx](axion/app/page.tsx)
- Main shell for the app and route-like view selection.
- Controls which major panel is visible in the UI.

### [axion/lib/api-client.ts](axion/lib/api-client.ts)
- Frontend API client for calling the FastAPI backend.
- Central place for all REST interactions from the UI.

### [axion/types/axion.ts](axion/types/axion.ts)
- Shared TypeScript interfaces for API responses and UI state.

### Major UI components
- [axion/components/axion/query-panel.tsx](axion/components/axion/query-panel.tsx): main question-answering interface
- [axion/components/axion/knowledge-graph.tsx](axion/components/axion/knowledge-graph.tsx): graph visualization view
- [axion/components/axion/contradiction-list.tsx](axion/components/axion/contradiction-list.tsx): contradiction browser
- [axion/components/axion/gap-list.tsx](axion/components/axion/gap-list.tsx): research gaps view
- [axion/components/axion/timeline-view.tsx](axion/components/axion/timeline-view.tsx): temporal analysis view
- [axion/components/axion/graph-evolution.tsx](axion/components/axion/graph-evolution.tsx): confidence evolution dashboard
- [axion/components/axion/ingestion-status.tsx](axion/components/axion/ingestion-status.tsx): ingestion progress and manual trigger UI
- [axion/components/axion/dashboard-stats.tsx](axion/components/axion/dashboard-stats.tsx): summary statistics cards

### UI support files
- [axion/components/ui](axion/components/ui): reusable shadcn-style UI primitives
- [axion/components/theme-provider.tsx](axion/components/theme-provider.tsx): theme wrapper
- [axion/hooks/use-mobile.ts](axion/hooks/use-mobile.ts): responsive behavior helper
- [axion/hooks/use-toast.ts](axion/hooks/use-toast.ts): toast state helper

---

## 10. Tests

### [tests/test_agents.py](tests/test_agents.py)
- Agent behavior and pipeline sanity tests.

### [tests/test_neo4j.py](tests/test_neo4j.py)
- Neo4j integration tests.

### [tests/test_phase4.py](tests/test_phase4.py)
- Coverage for structured claims and related Phase 4 functionality.

### [tests/test_phase5.py](tests/test_phase5.py)
- Coverage for later-phase features including graph and retrieval updates.

### [tests/test_axion.py](tests/test_axion.py)
- High-level regression or smoke coverage for the repository.

---

## 11. Dependency Notes and Maintenance Priorities

### Highest-impact files to understand first
1. [agents/coordinator_v2.py](agents/coordinator_v2.py)
2. [agents/reader.py](agents/reader.py)
3. [agents/contradiction.py](agents/contradiction.py)
4. [graph/neo4j_queries.py](graph/neo4j_queries.py)
5. [embeddings/store.py](embeddings/store.py)
6. [api/main.py](api/main.py)
7. [llm.py](llm.py)

### Files most likely to be edited for feature work
- Adding new agent behaviors: [agents](agents)
- Changing API responses: [api/main.py](api/main.py) and [api/models.py](api/models.py)
- Changing persistence semantics: [graph/neo4j_queries.py](graph/neo4j_queries.py)
- Changing retrieval behavior: [embeddings/store.py](embeddings/store.py)
- Changing ingestion behavior: [ingestion/arxiv_client.py](ingestion/arxiv_client.py), [ingestion/pdf_parser.py](ingestion/pdf_parser.py), and [agents/reader.py](agents/reader.py)
- Updating UI panels: [axion/components/axion](axion/components/axion)

### Files that are mostly support utilities
- [utils/logger.py](utils/logger.py)
- [utils/llm_parser.py](utils/llm_parser.py)
- [utils/llm_cache.py](utils/llm_cache.py)
- [utils/metrics.py](utils/metrics.py)
- [graph/backup.py](graph/backup.py)

---

## 12. Recommended Reading Order

For a new contributor, the fastest path is:
1. [README.md](README.md)
2. [AI_CONTEXT.md](AI_CONTEXT.md)
3. [main.py](main.py)
4. [agents/coordinator_v2.py](agents/coordinator_v2.py)
5. [agents/reader.py](agents/reader.py)
6. [graph/neo4j_queries.py](graph/neo4j_queries.py)
7. [embeddings/store.py](embeddings/store.py)
8. [api/main.py](api/main.py)
9. [axion/app/page.tsx](axion/app/page.tsx)

This order follows the product lifecycle from ingestion to query execution and UI rendering.
