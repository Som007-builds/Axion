# api/main.py
"""
Axion FastAPI backend.
Wraps all existing Python functions as HTTP endpoints.
Run with: uvicorn api.main:app --reload --port 8000
"""

import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Header, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import json
import secrets
import config

# Initialize logging configuration using LOG_LEVEL
LOG_LEVEL_STR = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_STR, logging.INFO)
logging.basicConfig(
    level=LOG_LEVEL,
    format="[%(asctime)s] %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from api.models import (
    GraphStats, ClaimsResponse, ContradictionsResponse, ContradictionModel,
    ExperimentModel, GapsResponse, CoordinatorOutput, IngestionSummary,
    ConfidenceDistribution, ChangedClaim, TemporalEvolution, DisputeTimeline
)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    Application lifespan: verify optional dependencies at boot (the API must
    start even when Neo4j/ChromaDB are down so /api/health can report
    "degraded"), and start/stop the in-process scheduler when enabled.
    """
    # ─── Startup ────────────────────────────────────────────────────────────
    logger.info("Running Axion backend startup checks...")

    try:
        from graph.neo4j_client import run_query
        run_query("RETURN 1")
        logger.info("Neo4j database connection verified.")
    except Exception as e:
        logger.warning(f"Neo4j is unreachable at startup (API will run degraded): {e}")

    try:
        from embeddings.store import collection_stats
        collection_stats()
        logger.info("ChromaDB vector database connection verified.")
    except Exception as e:
        logger.warning(f"ChromaDB is unreachable at startup (API will run degraded): {e}")

    try:
        from graph.neo4j_queries import get_graph_stats
        stats = get_graph_stats()
        claims_count = stats.get("claims", 0)
        logger.info(f"Axion startup complete: {claims_count} claims loaded in Neo4j.")
        logger.info(f"Active Groq LLM model configured: {config.GROQ_MODEL}")
    except Exception as e:
        logger.warning(f"Failed to log database stats on startup: {e}")

    if config.SCHEDULER_ENABLED:
        try:
            from ingestion.scheduler import start_scheduler
            start_scheduler()
            logger.warning(
                "Ingestion scheduler started in the API process. This requires a "
                "single worker (uvicorn --workers 1); multiple workers would run "
                "duplicate ingestion cycles."
            )
        except Exception as e:
            logger.error(f"Failed to start ingestion scheduler: {e}")

    yield

    # ─── Shutdown ───────────────────────────────────────────────────────────
    if config.SCHEDULER_ENABLED:
        try:
            from ingestion.scheduler import stop_scheduler
            stop_scheduler()
        except Exception as e:
            logger.warning(f"Failed to stop ingestion scheduler cleanly: {e}")


limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
app = FastAPI(
    title="Axion API",
    description="Multi-agent AI research knowledge graph",
    version="1.70",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )

# Allow Next.js (3000) or React (5173) dev server to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _write_secrets() -> tuple:
    """
    Secrets accepted by write/compute endpoints.

    `AXION_API_KEY` (header `X-API-Key`) is the preferred secret;
    `TRIGGER_SECRET` (header `X-Trigger-Secret`) is still accepted for
    backwards compatibility with existing deployments.
    """
    return tuple(s for s in (config.API_KEY, config.TRIGGER_SECRET) if s)


def _secret_matches(supplied: Optional[str], expected: tuple) -> bool:
    return bool(supplied) and any(secrets.compare_digest(supplied, e) for e in expected)


def require_write_access(
    x_api_key: Optional[str] = Header(None),
    x_trigger_secret: Optional[str] = Header(None),
) -> None:
    """
    Fail-closed auth guard for write/compute endpoints.

    If the server has neither AXION_API_KEY nor TRIGGER_SECRET configured, the
    endpoints are disabled entirely (503) rather than left open to anonymous
    callers. Otherwise a valid key must be supplied (401).
    """
    expected = _write_secrets()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Compute endpoints are disabled: AXION_API_KEY is not configured on the server.",
        )
    if not (_secret_matches(x_api_key, expected) or _secret_matches(x_trigger_secret, expected)):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def require_trigger_secret(x_trigger_secret: Optional[str]) -> None:
    """Deprecated: prefer `require_write_access`. Kept for compatibility."""
    require_write_access(x_api_key=None, x_trigger_secret=x_trigger_secret)


def format_experiment_for_frontend(exp_dict: dict) -> dict:
    e = exp_dict.get("experiment", {})
    caveats_val = exp_dict.get("caveats", "")
    if isinstance(caveats_val, str):
        caveats_list = [caveats_val] if caveats_val else []
    elif isinstance(caveats_val, list):
        caveats_list = caveats_val
    else:
        caveats_list = []
        
    return {
        "contradiction_id": exp_dict.get("contradiction_id", ""),
        "title": e.get("title", "Experiment Design"),
        "hypothesis_a": exp_dict.get("hypothesis_a", ""),
        "hypothesis_b": exp_dict.get("hypothesis_b", ""),
        "procedure": e.get("procedure", ""),
        "dataset": e.get("dataset", ""),
        "duration": e.get("expected_duration", ""),
        "cost": e.get("cost_estimate", ""),
        "decision_rule": exp_dict.get("decision_rule", ""),
        "caveats": caveats_list,
        "design_confidence": exp_dict.get("confidence_in_design", 0.0),
        "metric": e.get("metric", "Primary metric to measure"),
    }



# ─── Graph Stats ──────────────────────────────────────────────────────────────

@app.get("/api/stats", response_model=GraphStats)
def get_stats():
    from graph.neo4j_queries import get_graph_stats
    from graph.neo4j_client import run_query
    stats = get_graph_stats()
    
    # Query count of experiments
    exp_res = run_query("MATCH ()-[r:CONTRADICTS]->() WHERE r.experiment_design IS NOT NULL RETURN count(r) AS n")
    exp_count = exp_res[0]["n"] if exp_res else 0
    
    return {
        "papers": stats.get("papers", 0),
        "claims": stats.get("claims", 0),
        "contradictions": stats.get("contradictions", 0),
        "gaps": stats.get("gaps", 0),
        "experiments": exp_count
    }


# ─── Claims ───────────────────────────────────────────────────────────────────

@app.get("/api/claims", response_model=ClaimsResponse)
def get_claims(limit: int = 50, offset: int = 0):
    from graph.neo4j_queries import get_all_claims
    claims = get_all_claims()
    formatted_claims = []
    for c in claims:
        formatted_claims.append({
            "id": str(c.get("id")),
            "text": c.get("text", ""),
            "section": c.get("section", ""),
            "confidence": c.get("confidence", 0.0),
            "base_confidence": c.get("base_confidence"),
            "arxiv_id": c.get("arxiv_id", ""),
            "paper_year": c.get("paper_year"),
            "paper_title": c.get("paper_title"),
            # Phase 7: provenance fields
            "evidence_span": c.get("evidence_span", ""),
            "subject": c.get("subject", ""),
            "metric": c.get("metric", ""),
            "direction": c.get("direction", ""),
        })
    return {
        "total": len(formatted_claims),
        "claims": formatted_claims[offset:offset + limit]
    }


# Phase 7: Provenance endpoint
@app.get("/api/claims/{claim_id}/provenance")
def get_claim_provenance(claim_id: str):
    """
    Return the full provenance chain for a single claim:
    claim text, evidence_span, section, and the source paper metadata.
    """
    from graph.neo4j_client import run_query
    result = run_query("""
        MATCH (c:Claim) WHERE elementId(c) = $claim_id
        MATCH (c)-[:EXTRACTED_FROM]->(p:Paper)
        RETURN
            elementId(c)        AS claim_id,
            c.text              AS claim_text,
            c.evidence_span     AS evidence_span,
            c.section           AS section,
            c.confidence        AS confidence,
            c.subject           AS subject,
            c.predicate         AS predicate,
            c.object_val        AS object_val,
            c.metric            AS metric,
            c.direction         AS direction,
            c.conditions        AS conditions,
            p.arxiv_id          AS arxiv_id,
            p.title             AS title,
            p.authors           AS authors,
            p.published         AS published,
            p.citation_count    AS citation_count
    """, {"claim_id": claim_id})

    if not result:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found.")

    row = result[0]
    return {
        "claim_id":    row.get("claim_id"),
        "claim_text":  row.get("claim_text"),
        "evidence_span": row.get("evidence_span") or "",
        "section":     row.get("section"),
        "confidence":  row.get("confidence"),
        "structured": {
            "subject":    row.get("subject") or "",
            "predicate":  row.get("predicate") or "",
            "object_val": row.get("object_val") or "",
            "metric":     row.get("metric") or "",
            "direction":  row.get("direction") or "unclear",
            "conditions": row.get("conditions") or "{}",
        },
        "paper": {
            "arxiv_id":       row.get("arxiv_id"),
            "title":          row.get("title"),
            "authors":        row.get("authors") or [],
            "published":      row.get("published"),
            "citation_count": row.get("citation_count"),
            "url":            f"https://arxiv.org/abs/{row.get('arxiv_id')}",
        },
    }


# ─── Contradictions ───────────────────────────────────────────────────────────

@app.get("/api/contradictions", response_model=ContradictionsResponse)
def get_contradictions(min_confidence: float = 0.0, limit: int = 50):
    from graph.neo4j_queries import get_contradictions
    from agents.experiment_recommender import get_experiment_for_contradiction
    all_c = get_contradictions()
    filtered = [c for c in all_c if c.get("confidence", 0) >= min_confidence]
    
    formatted = []
    for c in filtered[:limit]:
        exp = get_experiment_for_contradiction(c["id"])
        
        formatted.append({
            "id": str(c["id"]),
            "claim_a": {
                "id": str(c.get("claim_a_id", "")),
                "text": c.get("claim_a", ""),
                "section": c.get("claim_a_section") or "Unknown",
                "confidence": c.get("claim_a_confidence", 0.0) or 0.0,
                "arxiv_id": c.get("paper_a_arxiv_id") or ""
            },
            "claim_b": {
                "id": str(c.get("claim_b_id", "")),
                "text": c.get("claim_b", ""),
                "section": c.get("claim_b_section") or "Unknown",
                "confidence": c.get("claim_b_confidence", 0.0) or 0.0,
                "arxiv_id": c.get("paper_b_arxiv_id") or ""
            },
            "paper_a": c.get("paper_a", ""),
            "paper_b": c.get("paper_b", ""),
            "explanation": c.get("explanation", ""),
            "confidence": c.get("confidence", 0.0),
            "has_experiment": exp is not None
        })
        
    return {
        "total": len(filtered),
        "contradictions": formatted
    }


# ─── Experiments ──────────────────────────────────────────────────────────────

@app.get("/api/experiments/{contradiction_id}", response_model=ExperimentModel)
def get_experiment(contradiction_id: str):
    from agents.experiment_recommender import get_experiment_for_contradiction
    exp = get_experiment_for_contradiction(contradiction_id)
    if not exp:
        raise HTTPException(status_code=404, detail="No experiment designed yet")
    return format_experiment_for_frontend(exp)


@app.post("/api/experiments/{contradiction_id}/design", response_model=ExperimentModel)
@limiter.limit("5/minute")
def design_experiment(contradiction_id: str, request: Request, _auth: None = Depends(require_write_access)):
    """Design an experiment for a specific contradiction on demand."""
    from graph.neo4j_queries import get_contradictions
    from agents.experiment_recommender import design_experiment, store_experiment

    all_c = get_contradictions()
    contradiction = next((c for c in all_c if str(c["id"]) == contradiction_id), None)
    if not contradiction:
        raise HTTPException(status_code=404, detail="Contradiction not found")

    exp = design_experiment(contradiction)
    if not exp:
        raise HTTPException(status_code=500, detail="Experiment design failed")

    store_experiment(contradiction_id, exp)
    return format_experiment_for_frontend(exp)


# ─── Research Gaps ────────────────────────────────────────────────────────────

@app.get("/api/gaps", response_model=GapsResponse)
def get_gaps(source: Optional[str] = None):
    from graph.neo4j_queries import get_gaps
    gaps = get_gaps()
    if source:
        gaps = [g for g in gaps if g.get("source") == source]
        
    formatted = []
    for g in gaps:
        formatted.append({
            "id": str(g.get("id")),
            "text": g.get("text", ""),
            "source": g.get("source", "llm_synthesized"),
            "related_claims": [str(cid) for cid in g.get("related_claims", [])],
            "confidence": g.get("confidence")
        })
        
    return {"total": len(formatted), "gaps": formatted}


# ─── Coordinator ──────────────────────────────────────────────────────────────

@app.post("/api/query", response_model=CoordinatorOutput)
@limiter.limit("10/minute")
def run_query(body: dict, request: Request, _auth: None = Depends(require_write_access)):
    """
    Run the coordinator v2 on a research question.
    Body: {"question": "your question here"}
    """
    question = body.get("question", "")
    question = question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    if len(question) > 500:
        raise HTTPException(status_code=422, detail="Question must not exceed 500 characters")

    from agents.coordinator_v2 import run
    output = run(question, verbose=False)
    
    # Extract confidence mapping
    raw_result = output.get("raw", {})
    conf_str = raw_result.get("confidence_in_answer", "medium").lower()
    conf_map = {"high": 0.9, "medium": 0.6, "low": 0.3}
    confidence_num = conf_map.get(conf_str, 0.6)
    
    # Extract unique cited sources (arxiv IDs)
    sources = set()
    for item in raw_result.get("consensus", []):
        for cit in item.get("citations", []):
            if cit:
                sources.add(str(cit))
    for item in raw_result.get("disputed", []):
        pa = item.get("position_a", {})
        pb = item.get("position_b", {})
        if isinstance(pa, dict) and pa.get("paper"):
            sources.add(str(pa["paper"]))
        if isinstance(pb, dict) and pb.get("paper"):
            sources.add(str(pb["paper"]))
            
    # Format plan as list of string subqueries for the frontend
    raw_plan = output.get("plan", {})
    sub_queries = raw_plan.get("sub_queries", [])
    
    # Map reflection log to match ReflectionStep schema
    reflection_log = []
    for step in output.get("reflection_log", []):
        reflection_log.append({
            "step": step.get("iteration", 1),
            "action": f"Iteration {step.get('iteration', 1)} reflection",
            "observation": step.get("assessment", ""),
            "reasoning": f"Query refined: {step.get('refined_query')}" if step.get("refined_query") else "Context marked sufficient"
        })
        
    return {
        "report": output.get("report", ""),
        "raw": json.dumps(raw_result),
        "iterations": output.get("iterations", 1),
        "plan": sub_queries,
        "reflection_log": reflection_log,
        "confidence": confidence_num,
        "sources": list(sources)
    }


# ─── Temporal Reasoning ───────────────────────────────────────────────────────

@app.get("/api/temporal/evolution", response_model=TemporalEvolution)
def get_evolution(
    topic: str,
    year_start: int = 2020,
    year_end: int = 2025
):
    from agents.temporal import get_consensus_evolution
    res = get_consensus_evolution(topic, year_start, year_end)

    overall_confidence = res.get("confidence")
    yearly_positions = []
    for pos in res.get("yearly_positions", []) or []:
        if not isinstance(pos, dict):
            continue
        try:
            year = int(pos.get("year"))
        except (TypeError, ValueError):
            continue  # skip positions without a usable year rather than inventing one

        conf = pos.get("confidence", overall_confidence)
        if not isinstance(conf, (int, float)):
            conf = 0.0

        yearly_positions.append({
            "year": year,
            "position": pos.get("position", ""),
            "confidence": float(conf),
            "key_papers": pos.get("key_claim_arxiv_ids", []) or []
        })

    return {
        "topic": topic,
        "yearly_positions": yearly_positions,
        "narrative": res.get("overall_narrative", ""),
        "current_status": res.get("current_status", "fragmented")
    }


@app.get("/api/temporal/disputes", response_model=DisputeTimeline)
def get_disputes(topic: str):
    from agents.temporal import get_contradiction_timeline
    res = get_contradiction_timeline(topic)

    claim_text_by_id = res.get("claim_text_by_id", {}) or {}
    disputes = []
    for i, d in enumerate(res.get("disputes", []) or []):
        if not isinstance(d, dict):
            continue

        status = str(d.get("status", "")).lower()
        first = d.get("first_appeared")
        resolution_year = d.get("resolution_year")

        raw_ids = d.get("related_claim_ids") or []
        key_claims = []
        for cid in raw_ids:
            cid = str(cid)
            text = claim_text_by_id.get(cid) or cid
            if isinstance(text, str) and len(text) > 90:
                text = text[:87].rstrip() + "..."
            key_claims.append(text)

        disputes.append({
            "id": str(d.get("id") or f"dispute-{i + 1}"),
            "topic": d.get("description") or d.get("explanation") or "Unspecified dispute",
            "start_year": int(first) if isinstance(first, (int, float)) else None,
            "end_year": int(resolution_year) if isinstance(resolution_year, (int, float)) else None,
            "resolved": status == "resolved",
            "resolution": d.get("resolution"),
            "key_claims": key_claims
        })

    return {
        "topic": topic,
        "disputes": disputes
    }


# ─── Confidence ───────────────────────────────────────────────────────────────

@app.get("/api/confidence/distribution", response_model=ConfidenceDistribution)
def confidence_distribution():
    from agents.confidence_updater import get_confidence_distribution
    dist = get_confidence_distribution()
    return {
        "total": dist.get("total", 0),
        "average": dist.get("avg_confidence", 0.0) or 0.0,
        "high": dist.get("high_confidence", 0),
        "medium": dist.get("medium_confidence", 0),
        "low": dist.get("low_confidence", 0)
    }


@app.get("/api/confidence/most-changed", response_model=list[ChangedClaim])
def most_changed(limit: int = 10):
    from agents.confidence_updater import get_most_changed_claims
    raw_changed = get_most_changed_claims(limit=limit)
    
    results = []
    for c in raw_changed:
        supports = c.get("supports", 0) or 0
        contradictions = c.get("contradictions", 0) or 0
        reason = f"{supports} support{'s' if supports != 1 else ''}, {contradictions} contradiction{'s' if contradictions != 1 else ''}"
        
        results.append({
            "claim_id": str(c.get("claim_id")),
            "claim_text": c.get("text", ""),
            "base_confidence": c.get("base", 0.0),
            "current_confidence": c.get("current", 0.0),
            "delta": c.get("delta", 0.0),
            "reason": reason
        })
    return results


@app.post("/api/confidence/recalculate")
@limiter.limit("2/minute")
def recalculate_confidence(request: Request, _auth: None = Depends(require_write_access)):
    from agents.confidence_updater import recalculate_all
    summary = recalculate_all()
    return {"updated": summary.get("total_updated", 0)}


# ─── Ingestion ────────────────────────────────────────────────────────────────

@app.get("/api/ingestion/status", response_model=IngestionSummary)
def ingestion_status():
    from ingestion.scheduler import get_run_log, is_running
    from ingestion.progress import progress_tracker

    running = is_running() or progress_tracker.get_progress().get("running", False)

    log = get_run_log()
    if not log:
        return {
            "new_papers": 0,
            "new_claims": 0,
            "last_run": None,
            "running": running
        }
    last = log[-1]
    return {
        "new_papers": last.get("papers_added", 0),
        "new_claims": last.get("claims_added", 0),
        "last_run": last.get("timestamp"),
        "running": running
    }


@app.post("/api/ingestion/trigger")
@limiter.limit("2/minute")
def trigger_ingestion(background_tasks: BackgroundTasks, request: Request, _auth: None = Depends(require_write_access)):
    """Trigger an ingestion cycle in the background (requires an API key)."""

    from ingestion.scheduler import trigger_now
    background_tasks.add_task(trigger_now)
    return {"status": "ingestion started in background"}


@app.post("/api/ingestion/custom")
@limiter.limit("5/minute")
def trigger_custom_ingestion(
    body: dict,
    background_tasks: BackgroundTasks,
    request: Request,
    _auth: None = Depends(require_write_access)
):
    """Trigger a custom ingestion cycle with a specific topic and paper count limit (requires an API key)."""

    from ingestion.progress import progress_tracker
    from ingestion.scheduler import is_running
    if is_running() or progress_tracker.get_progress()["running"]:
        raise HTTPException(status_code=409, detail="An ingestion pipeline is already running")

    topic = body.get("topic", "").strip()
    limit = body.get("limit", 5)

    if not topic:
        raise HTTPException(status_code=400, detail="topic is required")
    try:
        limit = int(limit)
        if limit <= 0 or limit > 50:
            raise ValueError()
    except ValueError:
        raise HTTPException(status_code=422, detail="limit must be an integer between 1 and 50")

    from ingestion.scheduler import run_custom_ingestion
    background_tasks.add_task(run_custom_ingestion, topic, limit)
    return {"status": "custom ingestion started in background"}


@app.get("/api/ingestion/progress")
def get_custom_ingestion_progress():
    """Retrieve the real-time status and logs of the active custom ingestion run."""
    from ingestion.progress import progress_tracker
    return progress_tracker.get_progress()


# ─── Knowledge Graph ──────────────────────────────────────────────────────────

@app.get("/api/graph")
def get_graph_data(limit_claims: int = 100):
    from graph.neo4j_client import run_query

    nodes = []
    edges = []

    # Papers
    papers = run_query("MATCH (p:Paper) RETURN p.arxiv_id AS id, p.title AS title, p.year AS year LIMIT 50")
    for p in papers:
        nodes.append({
            "id": f"paper_{p['id']}",
            "label": p["title"][:30] if p["title"] else p["id"],
            "type": "paper",
            "year": p.get("year")
        })

    # Claims
    claims = run_query(f"""
        MATCH (c:Claim)-[:EXTRACTED_FROM]->(p:Paper)
        RETURN elementId(c) AS id, c.text AS text,
               c.confidence AS confidence, p.arxiv_id AS arxiv_id
        LIMIT {limit_claims}
    """)
    for c in claims:
        nodes.append({
            "id": f"claim_{c['id']}",
            "label": c["text"][:30],
            "type": "claim",
            "confidence": c["confidence"]
        })
        edges.append({
            "source": f"claim_{c['id']}",
            "target": f"paper_{c['arxiv_id']}",
            "type": "EXTRACTED_FROM"
        })

    # Contradictions
    contras = run_query("""
        MATCH (a:Claim)-[r:CONTRADICTS]->(b:Claim)
        RETURN elementId(a) AS a_id, elementId(b) AS b_id,
               r.explanation AS explanation, r.confidence AS confidence
        LIMIT 100
    """)
    for r in contras:
        edges.append({
            "source": f"claim_{r['a_id']}",
            "target": f"claim_{r['b_id']}",
            "type": "CONTRADICTS"
        })

    # Gaps
    gaps = run_query("""
        MATCH (g:Gap)
        RETURN elementId(g) AS id, g.text AS text
        LIMIT 30
    """)
    for g in gaps:
        nodes.append({
            "id": f"gap_{g['id']}",
            "label": g["text"][:30],
            "type": "gap"
        })

    return {"nodes": nodes, "edges": edges}


# Startup/shutdown now live in the `lifespan` handler near the top of this file.


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/healthz")
def healthz():
    """
    Liveness probe: process is up and serving. Always 200.

    Deliberately does NOT check Neo4j/ChromaDB — a datastore outage is a
    readiness problem (see /api/health), not a reason to restart the container.
    """
    return {"status": "ok"}


@app.get("/api/health")
def health():
    """Quick health check — verifies Neo4j and ChromaDB are reachable."""
    neo4j_status = "connected"
    chromadb_status = "connected"
    claims_count = 0
    errors = []

    # 1. Test Neo4j
    try:
        from graph.neo4j_queries import get_graph_stats
        stats = get_graph_stats()
        claims_count = stats.get("claims", 0)
    except Exception as e:
        neo4j_status = "disconnected"
        logger.warning(f"Health check: Neo4j unreachable: {e}")
        errors.append("Neo4j unreachable")

    # 2. Test ChromaDB
    try:
        from embeddings.store import collection_stats
        collection_stats()
    except Exception as e:
        chromadb_status = "disconnected"
        logger.warning(f"Health check: ChromaDB unreachable: {e}")
        errors.append("ChromaDB unreachable")

    if neo4j_status == "disconnected" or chromadb_status == "disconnected":
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "neo4j": neo4j_status,
                "chromadb": chromadb_status,
                "claims": claims_count,
                "errors": errors
            }
        )

    return {
        "status": "ok",
        "neo4j": neo4j_status,
        "chromadb": chromadb_status,
        "claims": claims_count
    }


# ─── Metrics (Phase 9) ───────────────────────────────────────────────────────

@app.get("/api/metrics")
def get_metrics():
    """
    Production observability endpoint.
    Returns aggregated metrics for LLM calls, ingestion runs,
    contradiction detection, and graph writes.
    Also includes LLM cache statistics if caching is enabled.
    """
    try:
        from utils.metrics import metrics
        summary = metrics.get_summary()
    except Exception as e:
        logger.warning(f"Failed to collect metrics: {e}")
        summary = {"error": "metrics unavailable"}

    # Attach LLM cache stats if cache is active
    try:
        import config as _config
        if _config.LLM_CACHE_ENABLED:
            from utils.llm_cache import cache_stats
            summary["llm_cache"] = cache_stats()
        else:
            summary["llm_cache"] = {"enabled": False}
    except Exception:
        pass

    return summary
