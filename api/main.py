# api/main.py
"""
Axion FastAPI backend.
Wraps all existing Python functions as HTTP endpoints.
Run with: uvicorn api.main:app --reload --port 8000
"""

import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Header, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
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
    ExperimentModel, GapsResponse, IngestionSummary,
    ConfidenceDistribution, ChangedClaim, TemporalEvolution, DisputeTimeline
)
from api.gap_sources import (
    FILTER_SOURCES,
    count_gap_sources,
    normalize_gap_source,
    source_description,
    source_label,
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
                "arxiv_id": c.get("paper_a_arxiv_id") or "",
                "paper_title": c.get("paper_a"),
                "evidence_span": c.get("claim_a_evidence_span"),
                "subject": c.get("claim_a_subject"),
                "predicate": c.get("claim_a_predicate"),
                "object_val": c.get("claim_a_object_val"),
                "metric": c.get("claim_a_metric"),
                "direction": c.get("claim_a_direction"),
                "conditions": c.get("claim_a_conditions"),
            },
            "claim_b": {
                "id": str(c.get("claim_b_id", "")),
                "text": c.get("claim_b", ""),
                "section": c.get("claim_b_section") or "Unknown",
                "confidence": c.get("claim_b_confidence", 0.0) or 0.0,
                "arxiv_id": c.get("paper_b_arxiv_id") or "",
                "paper_title": c.get("paper_b"),
                "evidence_span": c.get("claim_b_evidence_span"),
                "subject": c.get("claim_b_subject"),
                "predicate": c.get("claim_b_predicate"),
                "object_val": c.get("claim_b_object_val"),
                "metric": c.get("claim_b_metric"),
                "direction": c.get("claim_b_direction"),
                "conditions": c.get("claim_b_conditions"),
            },
            "paper_a": c.get("paper_a", ""),
            "paper_b": c.get("paper_b", ""),
            "explanation": c.get("explanation", ""),
            "confidence": c.get("confidence", 0.0),
            "has_experiment": exp is not None
        })

    return {
        "total": len(filtered),
        "corpus_total": len(all_c),
        "shown": len(formatted),
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
    """
    Research gaps with a canonical source taxonomy.

    Stored sources are normalised at this boundary. ``sqlite_migration`` records
    are surfaced as ``legacy_import`` rather than guessed to be cluster or
    future-work gaps. ``source_counts`` always describes the whole corpus, so a
    filtered empty state can explain what else is available.
    """
    from graph.neo4j_queries import get_gaps, get_claim_references

    all_gaps = get_gaps()
    source_counts = count_gap_sources(all_gaps)

    requested_source: Optional[str] = None
    if source is not None and str(source).strip():
        candidate = str(source).strip().lower()
        if candidate not in FILTER_SOURCES:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Unsupported gap source filter. Use one of: "
                    + ", ".join(FILTER_SOURCES)
                ),
            )
        requested_source = candidate

    selected = [
        gap for gap in all_gaps
        if requested_source is None
        or normalize_gap_source(gap.get("source")) == requested_source
    ]

    # Resolve related claim IDs to readable text + paper provenance in one query.
    all_claim_ids = []
    for gap in selected:
        all_claim_ids.extend(str(cid) for cid in (gap.get("related_claims") or []) if cid)
    claim_refs: dict[str, dict] = {}
    if all_claim_ids:
        try:
            claim_refs = get_claim_references(list(dict.fromkeys(all_claim_ids)))
        except Exception as exc:  # never fail the whole list for enrichment
            logger.warning("Gap claim enrichment failed: %s", exc)

    formatted = []
    for gap in selected:
        raw_source = gap.get("source")
        canonical_source = normalize_gap_source(raw_source)
        related_ids = [str(cid) for cid in (gap.get("related_claims") or []) if cid]
        details = []
        for cid in related_ids:
            ref = claim_refs.get(cid)
            if not ref:
                continue
            details.append({
                "id": cid,
                "text": ref.get("text") or "",
                "section": ref.get("section"),
                "confidence": ref.get("confidence"),
                "arxiv_id": ref.get("arxiv_id"),
                "paper_title": ref.get("paper_title"),
            })

        formatted.append({
            "id": str(gap.get("id")),
            "text": gap.get("text", ""),
            "source": canonical_source,
            "source_raw": str(raw_source) if raw_source is not None else None,
            "source_label": source_label(canonical_source),
            "source_description": source_description(canonical_source),
            "related_claims": related_ids,
            "related_claim_details": details,
            "confidence": gap.get("confidence"),
        })

    return {
        "total": len(formatted),
        "corpus_total": source_counts["all"],
        "source_counts": source_counts,
        "gaps": formatted,
    }


# ─── Coordinator ──────────────────────────────────────────────────────────────

@app.post("/api/query", status_code=202)
@limiter.limit("10/minute")
def run_query(body: dict, request: Request, _auth: None = Depends(require_write_access)):
    """
    Queue a research query and return a job id immediately.

    The multi-iteration coordinator loop is far too slow to hold an HTTP
    request open (and would be lost on restart), so it runs as a background
    job. Poll `GET /api/jobs/{job_id}` until `status` is `completed`.

    Body: {"question": "your question here"}
    """
    question = str(body.get("question", "")).strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    if len(question) > 500:
        raise HTTPException(status_code=422, detail="Question must not exceed 500 characters")

    from jobs.backend import JOB_QUERY, submit
    job_id, backend = submit(JOB_QUERY, {"question": question})
    return {"job_id": job_id, "status": "queued", "backend": backend}


# ─── Background jobs ──────────────────────────────────────────────────────────

@app.get("/api/jobs")
def list_jobs(limit: int = 20, _auth: None = Depends(require_write_access)):
    """
    Most recent background jobs, newest first.

    `limit` is clamped to 1–100. Key-guarded like the single-job route, because
    a job record carries its result (research answers, ingestion summaries).
    """
    from jobs.store import get_job_store, public_view

    limit = max(1, min(limit, 100))
    records = get_job_store().list_recent(limit)
    return {"jobs": [public_view(record) for record in records]}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, _auth: None = Depends(require_write_access)):
    """
    Status and result of a background job.

    Returns `{id, kind, status, created_at, started_at, finished_at, result}`;
    `status` is one of `queued`, `running`, `completed`, `failed`. Requires the
    API key so job results are not readable with a guessed id.
    """
    from jobs.store import get_job_store, public_view

    record = get_job_store().get(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Job not found")
    return public_view(record)


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
def get_disputes(topic: str, year_start: int = 2019, year_end: int = 2026):
    from agents.temporal import get_contradiction_timeline
    res = get_contradiction_timeline(topic, year_start, year_end)

    claim_text_by_id = res.get("claim_text_by_id", {}) or {}
    disputes = []
    for i, d in enumerate(res.get("disputes", []) or []):
        if not isinstance(d, dict):
            continue

        status_raw = str(d.get("status", "")).strip().lower()
        status = status_raw if status_raw in {"active", "resolved", "fading"} else "unknown"
        first = d.get("first_appeared")
        resolution_year = d.get("resolution_year")

        raw_ids = d.get("related_claim_ids") or []
        key_claims = []
        seen_claims = set()
        for cid in raw_ids:
            text = claim_text_by_id.get(str(cid))
            if not isinstance(text, str) or not text.strip():
                # Never surface an opaque graph ID as if it were claim text.
                continue
            text = text.strip()
            if len(text) > 120:
                text = text[:117].rstrip() + "..."
            if text in seen_claims:
                continue
            seen_claims.add(text)
            key_claims.append(text)

        disputes.append({
            "id": str(d.get("id") or f"dispute-{i + 1}"),
            "topic": d.get("description") or d.get("explanation") or "Unspecified dispute",
            "start_year": int(first) if isinstance(first, (int, float)) else None,
            "end_year": int(resolution_year) if isinstance(resolution_year, (int, float)) else None,
            "resolved": status == "resolved",
            "status": status,
            "resolution": d.get("resolution"),
            "key_claims": key_claims
        })

    return {
        "topic": topic,
        "disputes": disputes,
        "summary": res.get("summary", "") or "",
        "candidate_claim_count": int(res.get("candidate_claim_count", 0) or 0),
        "contradiction_count": int(res.get("contradiction_count", 0) or 0),
        "year_start": int(res.get("year_start", year_start) or year_start),
        "year_end": int(res.get("year_end", year_end) or year_end),
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
            "reason": reason,
            "supports": supports,
            "contradictions": contradictions,
            "arxiv_id": c.get("arxiv_id"),
            "paper_title": c.get("paper_title"),
        })
    return results


@app.post("/api/confidence/recalculate")
@limiter.limit("2/minute")
def recalculate_confidence(request: Request, _auth: None = Depends(require_write_access)):
    from agents.confidence_updater import recalculate_all
    summary = recalculate_all()
    return {"updated": summary.get("total_updated", 0)}


# ─── Ingestion ────────────────────────────────────────────────────────────────

def _iso(timestamp: Optional[float]) -> Optional[str]:
    """Epoch seconds → ISO-8601 string (None-safe)."""
    if timestamp is None:
        return None
    from datetime import datetime
    return datetime.fromtimestamp(timestamp).isoformat()


def _latest_ingestion_job(store, status: str) -> Optional[dict]:
    """Most recent ingestion job in the given terminal status."""
    from jobs.backend import INGESTION_KINDS

    for record in store.list_recent(25):
        if record.get("kind") in INGESTION_KINDS and record.get("status") == status:
            return record
    return None


@app.get("/api/ingestion/status", response_model=IngestionSummary)
def ingestion_status():
    """
    Summary of the last ingestion run and whether one is in flight.

    Reads the durable job registry rather than process-local counters, so it
    stays accurate when ingestion runs in a separate worker process.
    """
    from ingestion.progress import progress_tracker
    from jobs.backend import active_ingestion_job
    from jobs.store import STATUS_COMPLETED, get_job_store

    running = (
        active_ingestion_job() is not None
        or progress_tracker.get_progress().get("running", False)
    )

    last = _latest_ingestion_job(get_job_store(), STATUS_COMPLETED)
    if not last:
        return {"new_papers": 0, "new_claims": 0, "last_run": None, "running": running}

    result = last.get("result") or {}
    return {
        "new_papers": result.get("papers_added", 0),
        "new_claims": result.get("claims_added", 0),
        "last_run": _iso(last.get("finished_at")),
        "running": running,
    }


@app.post("/api/ingestion/trigger", status_code=202)
@limiter.limit("2/minute")
def trigger_ingestion(request: Request, _auth: None = Depends(require_write_access)):
    """
    Queue an ingestion cycle across the configured topics (requires an API key).

    Returns a job id; poll `GET /api/jobs/{job_id}` for completion.
    """
    from jobs.backend import JOB_INGESTION, JobConflictError, submit

    try:
        job_id, backend = submit(JOB_INGESTION)
    except JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"status": "queued", "job_id": job_id, "backend": backend}


@app.post("/api/ingestion/custom", status_code=202)
@limiter.limit("5/minute")
def trigger_custom_ingestion(
    body: dict,
    request: Request,
    _auth: None = Depends(require_write_access)
):
    """
    Queue an ingestion cycle for a specific topic and paper limit (requires an API key).

    Returns a job id; live counters are on `GET /api/ingestion/progress`.
    """
    topic = str(body.get("topic", "")).strip()
    limit = body.get("limit", 5)

    if not topic:
        raise HTTPException(status_code=400, detail="topic is required")
    try:
        limit = int(limit)
        if limit <= 0 or limit > 50:
            raise ValueError()
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="limit must be an integer between 1 and 50")

    from jobs.backend import JOB_CUSTOM_INGESTION, JobConflictError, submit

    try:
        job_id, backend = submit(JOB_CUSTOM_INGESTION, {"topic": topic, "limit": limit})
    except JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"status": "queued", "job_id": job_id, "backend": backend}


@app.get("/api/ingestion/progress")
def get_custom_ingestion_progress():
    """
    Real-time status and logs of the active ingestion run.

    Works across processes: when ingestion runs in the worker, the counters are
    read from Redis. If a job is queued but no worker has claimed it yet, a
    synthetic `queued` snapshot is returned so clients do not fall back to an
    idle view in the gap between submit and start. Internal error text is not
    echoed to clients (full detail is in the server logs), matching the API's
    error-handling policy.
    """
    from ingestion.progress import progress_tracker
    from jobs.backend import active_ingestion_job

    progress = progress_tracker.get_progress()

    if progress.get("status") == "idle":
        job = active_ingestion_job()
        if job:
            payload = job.get("_payload") or {}
            progress = {
                **progress,
                "status": "queued",
                "topic": payload.get("topic", ""),
                "limit": payload.get("limit", 0),
                "current_step": "Waiting for a worker to pick up the job",
                "percent": 5,
                "running": True,
                "logs": [
                    f"Queued as job {job.get('id', '')} — waiting for the ingestion worker."
                ],
            }

    if progress.get("error_message"):
        progress["error_message"] = "Ingestion failed. Check the server logs for details."
    return progress


# ─── Knowledge Graph ──────────────────────────────────────────────────────────

@app.get("/api/graph")
def get_graph_data(limit_claims: int = 100):
    from graph.neo4j_client import run_query

    # Bound the request so the round-robin claim query cannot be used to pull
    # an unbounded slice into memory.
    limit_claims = max(1, min(limit_claims, 500))

    nodes = []
    edges = []

    # Relationship-bearing claims come first: the graph exists to expose
    # contradiction/support structure, and a purely arbitrary slice can hide
    # every relationship in the corpus. Remaining slots (at higher limits) are
    # filled by confidence.
    claims = run_query(f"""
        MATCH (c:Claim)-[:EXTRACTED_FROM]->(p:Paper)
        OPTIONAL MATCH (c)-[rel:CONTRADICTS|SUPPORTS]-()
        WITH c, p, count(rel) AS relationship_count
        ORDER BY relationship_count DESC, c.confidence DESC, p.arxiv_id ASC
        LIMIT {limit_claims}
        RETURN elementId(c) AS id, c.text AS text,
               c.section AS section,
               c.confidence AS confidence,
               p.arxiv_id AS arxiv_id,
               p.title AS paper_title,
               p.year AS year
    """)
    paper_nodes = {}
    for c in claims:
        arxiv_id = c.get("arxiv_id")
        if arxiv_id and arxiv_id not in paper_nodes:
            paper_nodes[arxiv_id] = {
                "id": f"paper_{arxiv_id}",
                "label": c.get("paper_title") or arxiv_id,
                "text": c.get("paper_title") or arxiv_id,
                "type": "paper",
                "year": c.get("year"),
                "arxiv_id": arxiv_id,
            }

    for c in claims:
        text = c["text"] or ""
        nodes.append({
            "id": f"claim_{c['id']}",
            "label": text[:100],
            "text": text,
            "type": "claim",
            "confidence": c["confidence"],
            "section": c.get("section"),
            "arxiv_id": c.get("arxiv_id"),
            "paper_title": c.get("paper_title"),
            "year": c.get("year")
        })
        if c.get("arxiv_id"):
            edges.append({
                "source": f"claim_{c['id']}",
                "target": f"paper_{c['arxiv_id']}",
                "type": "EXTRACTED_FROM"
            })

    nodes.extend(paper_nodes.values())

    # Contradictions. The frontend drops edges whose endpoints are outside the
    # selected claim limit, so no orphan links are drawn.
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

    supports = run_query("""
        MATCH (a:Claim)-[:SUPPORTS]->(b:Claim)
        RETURN elementId(a) AS a_id, elementId(b) AS b_id
        LIMIT 100
    """)
    for r in supports:
        edges.append({
            "source": f"claim_{r['a_id']}",
            "target": f"claim_{r['b_id']}",
            "type": "SUPPORTS"
        })

    # Gaps and their related claims
    gaps = run_query("""
        MATCH (g:Gap)
        OPTIONAL MATCH (g)-[:RELATED_TO]->(c:Claim)
        RETURN elementId(g) AS id, g.text AS text, g.source AS source,
               g.confidence AS confidence,
               collect(elementId(c)) AS related_claim_ids
        LIMIT 30
    """)
    for g in gaps:
        text = g["text"] or ""
        nodes.append({
            "id": f"gap_{g['id']}",
            "label": text[:100],
            "text": text,
            "type": "gap",
            "source": normalize_gap_source(g.get("source")),
            "confidence": g.get("confidence")
        })
        for claim_id in g.get("related_claim_ids") or []:
            if claim_id:
                edges.append({
                    "source": f"gap_{g['id']}",
                    "target": f"claim_{claim_id}",
                    "type": "RELATED_TO"
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
