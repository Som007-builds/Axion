# Axion

A multi-agent scientific intelligence system that reads AI research papers,
extracts empirical claims, detects contradictions between papers, and surfaces
research gaps the field hasn't answered yet.

**The core insight:** scientific knowledge is a network, not a document collection.
Two papers can agree on a topic but contradict each other on a specific finding.
Standard search engines can't detect that. Axion can — and it compounds
what it learns over time.


[![Technical Spec](https://img.shields.io/badge/Spec-AXION%20v2.30-blue?style=for-the-badge)](./AXION_SPEC.md)

---

## Live Stats
| Metric | Count |
|---|---|
| Papers ingested | 48 |
| Claims extracted | 2,389 |
| Contradictions detected | 224 |
| Suggests (support links) | 132 |
| Research gaps identified | 30 |
| Experiment designs | 12 |

---

## What Makes This Different From RAG

Standard RAG retrieves document chunks and summarizes them. Axion:

- **Operates at claim level** — every paper is decomposed into atomic, falsifiable assertions
- **Builds a persistent graph** — claims, contradictions, and gaps are stored as typed edges in Neo4j
- **Compounds over time** — each new paper is compared against all prior papers automatically
- **Self-corrects** — claim confidence scores recalculate as more papers support or contradict them

---

## Architecture

```
ArXiv Papers
     │
     ▼
┌─────────────────────────────────────────────┐
│              Agent 1: Reader                │
│  Extracts falsifiable claims per section    │
└──────────────────────┬──────────────────────┘
                       │ writes Claims to graph
          ┌────────────▼──────────────────────┐
          │         Knowledge Graph           │
          │   Neo4j + ChromaDB (vectors)      │
          └────────┬──────────────┬───────────┘
                   │              │
     ┌─────────────▼──┐    ┌──────▼──────────────┐
     │  Agent 2:      │    │  Agent 3: Gap Finder │
     │  Contradiction │    │  Reasons about what  │
     │  Detector      │    │  the field hasn't    │
     │                │    │  answered yet        │
     └─────────────┬──┘    └──────┬───────────────┘
                   │              │
          ┌────────▼──────────────▼───────────┐
          │    Enriched Knowledge Graph       │
          │  CONTRADICTS · SUPPORTS · RELATED │
          └────────────────┬──────────────────┘
                           │
          ┌────────────────▼──────────────────┐
          │        Agent 4: Coordinator v2    │
          │  Plan → Retrieve → Reflect →      │
          │  Synthesize (ReAct loop, max 3x)  │
          └───────────────────────────────────┘
```

---

## Key Capabilities

### Contradiction Detection
The system finds semantically similar claims across papers and asks an LLM to
judge the relationship. Every candidate pair is classified as exactly one of:

`CONTRADICTS` · `SUPPORTS` · `UNRELATED`

Contradictions and supports carry an LLM-written explanation and a confidence
score. Pairs from the same paper are never compared (a paper can't contradict
itself), and every finding is stored as a typed edge in Neo4j.

### Dynamic Confidence Propagation
Every claim has a confidence score that recalculates as new papers enter the graph:
```
confidence = base_confidence + (0.08 × supports) − (0.12 × contradictions)
```
Clamped to [0.05, 0.98]. A claim from 2022 contradicted by three 2024 papers
automatically loses confidence. The graph self-corrects.

### ReAct Coordinator Loop
User queries go through a multi-step reasoning loop:
1. **Plan** — generates 1-3 targeted sub-queries
2. **Retrieve** — searches ChromaDB + Neo4j
3. **Reflect** — scores context sufficiency (0-10), refines if <7
4. **Synthesize** — writes a cited research report

### Temporal Reasoning
Tracks how scientific consensus evolves year by year. The system can show
you that in 2022 the field agreed X, by 2023 contradictions appeared,
and by 2024 the position had fragmented.

### Experiment Recommender
For every high-confidence contradiction, the system designs the minimal
experiment to resolve it — specific dataset, model sizes, metric,
decision rule, cost estimate. Stored on the CONTRADICTS relationship in Neo4j.

---

## Running Locally

### Prerequisites
- Python 3.11+
- Node.js 20+
- Docker (for Neo4j)
- An LLM API key (Groq, Gemini, or Anthropic)

### Setup

```bash
# 1. Clone and install backend
git clone https://github.com/Som007-builds/Axion
cd Axion
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your API keys

# 3. Start Neo4j
docker compose up -d neo4j

# 4. Initialize the graph
python -m graph.neo4j_schema

# 5. Ingest papers
python main.py --mode ingest --query "chain of thought prompting LLM" --n 10

# 6. Run agents
python main.py --mode contradict
python main.py --mode confidence
python main.py --mode experiments

# 7. Start the API
uvicorn api.main:app --reload --port 8000

# 8. Start the frontend
cd axion && pnpm install && pnpm dev
# Opens at http://localhost:3000
```

---

## CLI Reference

```bash
python main.py --mode ingest       --query "..." --n 20   # Ingest papers
python main.py --mode contradict                           # Detect contradictions
python main.py --mode confidence                           # Recalculate scores
python main.py --mode gaps                                 # Find research gaps
python main.py --mode experiments                          # Design experiments
python main.py --mode citations                            # Fetch citation counts
python main.py --mode query     --query "..."              # Ask a research question
python main.py --mode schedule                             # Start auto-ingestion
python main.py --mode backup                               # Back up the graph
```

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Graph DB | Neo4j 5.x | Typed edges, Cypher traversal, native graph ops |
| Vector Store | ChromaDB | Local persistent embeddings, no API cost |
| Embeddings | all-MiniLM-L6-v2 | Local, free, 384-dim, fast |
| LLM | Claude / Groq / Gemini | Multi-provider fallback chain |
| Backend | FastAPI | Async-ready, auto-docs at /docs |
| Frontend | Next.js 16 + Tailwind | React component model, Axion workspace |
| Graph Viz | react-force-graph | Force-directed, 270+ nodes smooth |
| Scheduler | APScheduler | Background ingestion every 6 hours |
| PDF parsing | PyMuPDF | Section-aware, fast, text-layer PDFs |

---

## Project Structure

```
Axion/
├── agents/          # All reasoning agents
├── api/             # FastAPI endpoints
├── axion/           # Next.js frontend workspace
├── graph/           # Neo4j client, schema, Cypher queries
├── ingestion/       # ArXiv client, PDF parser, scheduler
├── embeddings/      # ChromaDB wrapper
├── eval/            # Evaluation harness (run_eval.py)
├── utils/           # Structured logging
├── archive/         # Deprecated SQLite layer (reference only)
├── tests/           # 111 offline unit tests (+ integration, opt-in)
├── main.py          # CLI entry point
└── AXION_SPEC.md    # Full technical specification
```

---

## Technical Specification

The full engineering specification (v2.30) is in [`AXION_SPEC.md`](./AXION_SPEC.md).
It covers the full architecture, agent system, graph schema, contradiction engine,
confidence system, and long-term vision.

---

## Known Limitations

- **Contradiction false positives:** The engine can flag complementary findings
  as contradictions when parameter scopes differ (e.g., 7B vs 70B models).
  There is currently no adversarial/red-team validation pass to filter these.
- **Linear confidence model:** The confidence formula
  (`base + 0.08×supports − 0.12×contradictions`) treats all papers equally
  regardless of citation count or venue quality. A separate citation-weighting
  helper exists but is not part of the default confidence path.
- **Synchronous work:** Large batch ingestion and `/api/query` run the full LLM
  loop inside the request/thread. A Celery/RQ task queue is the planned fix.
- **No authentication:** All read/query endpoints are open; only the two
  ingestion triggers require a shared secret.
- **Evaluation is not yet valid:** the labelled eval set's positive examples are
  all same-paper pairs, which the engine refuses to score (see
  [`eval/README.md`](./eval/README.md)). No trustworthy accuracy figure exists yet.
- **Single API worker only:** in-process scheduler, metrics, and ingestion
  progress are not safe across multiple workers.

---

## Built By

Soham Singh — 1st year BTech, 2nd semester.  
Built over 2 months as a solo project.

---

## License

MIT
