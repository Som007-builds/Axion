# ingestion/scheduler.py
"""
Continuous ingestion scheduler.

Fetches new ArXiv papers on a configurable interval (default: every 6 hours),
runs Agent 1 (Reader) on them, then triggers Agent 2 (Contradiction Detector).

Usage — embedded in Streamlit / main.py:
    from ingestion.scheduler import start_scheduler, stop_scheduler, trigger_now
    start_scheduler()

Usage — standalone:
    python ingestion/scheduler.py
"""
import time
import threading
from datetime import datetime
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

logger = logging.getLogger(__name__)


from config import SCHEDULER_TOPICS, SCHEDULER_INTERVAL_HOURS, SCHEDULER_PAPERS_PER_RUN
from ingestion.arxiv_client import search_papers, download_pdf
from agents.reader import process_paper
from agents.contradiction import run_contradiction_detection

# ─── Module-level state (accessible from UI thread) ──────────
_scheduler = None
_run_log: list[dict] = []   # [{timestamp, papers_added, claims_added, contradictions_found}]
_running = False            # True while an ingestion cycle is in flight
_lock = threading.Lock()


# ─── Internal helpers ─────────────────────────────────────────

def _log_run(papers_added: int, claims_added: int, contradictions_found: int):
    with _lock:
        _run_log.append({
            "timestamp": datetime.now().isoformat(),
            "papers_added": papers_added,
            "claims_added": claims_added,
            "contradictions_found": contradictions_found
        })
        # Keep only the last 50 entries
        if len(_run_log) > 50:
            _run_log.pop(0)


def _on_job_event(event):
    if event.exception:
        logger.error(f"[Scheduler] ❌ Job failed: {event.exception}")
    else:
        logger.info(f"[Scheduler] ✅ Job completed successfully")


def _ingestion_job():
    """
    Single ingestion run. Called by the scheduler on each tick.

    Guards against overlapping runs (max_instances only protects scheduled
    ticks, not manual triggers) and exposes running state to the API.
    """
    global _running
    with _lock:
        if _running:
            logger.warning("[Scheduler] Ingestion already running — skipping this tick.")
            return
        _running = True

    try:
        _run_ingestion_cycle()
    finally:
        with _lock:
            _running = False


def _run_ingestion_cycle():
    """
    Searches ArXiv for each configured topic, ingests new papers,
    then runs contradiction detection on newly added claims.
    """
    logger.info(f"\n[Scheduler] Starting ingestion run at {datetime.now().isoformat()}")

    total_papers = 0
    total_claims = 0

    processed_arxiv_ids = []
    for topic in SCHEDULER_TOPICS:
        logger.info(f"  Topic: '{topic}'")
        papers = search_papers(topic, max_results=SCHEDULER_PAPERS_PER_RUN)

        for paper in papers:
            try:
                pdf_path = download_pdf(paper["arxiv_id"])
                claims_added = process_paper(paper, pdf_path)
                total_papers += 1
                total_claims += (claims_added or 0)
                processed_arxiv_ids.append(paper["arxiv_id"])
            except Exception as e:
                logger.warning(f"  Warning: failed to process {paper['arxiv_id']}: {e}")

    logger.info(f"  Running contradiction detection on new claims...")
    try:
        from graph.neo4j_client import run_query
        if processed_arxiv_ids:
            res = run_query("""
                MATCH (c:Claim)-[:EXTRACTED_FROM]->(p:Paper)
                WHERE p.arxiv_id IN $arxiv_ids
                RETURN elementId(c) AS claim_id
            """, {"arxiv_ids": processed_arxiv_ids})
            new_claim_ids = [r["claim_id"] for r in res] if res else []
        else:
            new_claim_ids = []
        contradictions_found = run_contradiction_detection(limit_to_claim_ids=new_claim_ids)
    except Exception as e:
        logger.warning(f"  Warning: contradiction detection failed: {e}")
        contradictions_found = 0

    _log_run(total_papers, total_claims, contradictions_found)
    logger.info(
        f"[Scheduler] Run complete — "
        f"{total_papers} papers, {total_claims} claims, "
        f"{contradictions_found} contradictions"
    )


# ─── Public API ───────────────────────────────────────────────

def get_run_log() -> list[dict]:
    """Returns a copy of the ingestion run log. Thread-safe."""
    with _lock:
        return list(_run_log)


def is_running() -> bool:
    """True while a scheduled/manual ingestion cycle is in flight. Thread-safe."""
    with _lock:
        return _running


def start_scheduler() -> BackgroundScheduler:
    """
    Start the background ingestion scheduler.
    Idempotent — calling a second time returns the existing scheduler.
    """
    global _scheduler

    if _scheduler and _scheduler.running:
        logger.info("[Scheduler] Already running.")
        return _scheduler

    _scheduler = BackgroundScheduler()
    _scheduler.add_listener(_on_job_event, EVENT_JOB_ERROR | EVENT_JOB_EXECUTED)

    _scheduler.add_job(
        func=_ingestion_job,
        trigger="interval",
        hours=SCHEDULER_INTERVAL_HOURS,
        id="ingestion_job",
        name="ArXiv ingestion",
        max_instances=1,           # never overlap two runs
        coalesce=True,             # if multiple missed ticks, run once
        misfire_grace_time=3600    # 1-hour grace window
    )

    _scheduler.start()
    logger.info(
        f"[Scheduler] Started — interval: every {SCHEDULER_INTERVAL_HOURS}h, "
        f"topics: {len(SCHEDULER_TOPICS)}"
    )
    return _scheduler


def stop_scheduler():
    """Gracefully stop the background scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Stopped.")


def trigger_now():
    """Run one ingestion job immediately, outside the normal schedule."""
    logger.info("[Scheduler] Manual trigger...")
    _ingestion_job()


def run_custom_ingestion(topic: str, limit: int):
    """
    Run a custom user-defined ingestion job in the background, logging
    all sub-agent steps and pipeline stats to the progress tracker.
    """
    from ingestion.progress import progress_tracker
    from agents.confidence_updater import recalculate_all
    import time

    try:
        progress_tracker.start(topic, limit)

        # 1. Search papers
        progress_tracker.add_log("Querying ArXiv API...")
        papers = search_papers(topic, max_results=limit)

        if not papers:
            progress_tracker.add_log("No new papers found matching the query topic.")
            progress_tracker.complete(0)
            return

        progress_tracker.add_log(f"Found {len(papers)} papers on ArXiv. Starting ingestion...")

        # 2. Process papers
        progress_tracker.update_status("processing", "Ingesting papers")

        for idx, paper in enumerate(papers, start=1):
            arxiv_id = paper["arxiv_id"]
            title = paper["title"]

            progress_tracker.start_paper(idx, arxiv_id, title)
            start_paper_time = time.time()

            try:
                progress_tracker.update_paper_step("Downloading PDF from ArXiv")
                pdf_path = download_pdf(arxiv_id)

                progress_tracker.update_paper_step("Parsing text & extracting claims (Reader Agent)")
                claims_added = process_paper(paper, pdf_path)

                elapsed = time.time() - start_paper_time
                progress_tracker.finish_paper(elapsed, claims_added or 0)
            except Exception as e:
                progress_tracker.add_log(f"Error processing paper {arxiv_id}: {str(e)}")
                progress_tracker.finish_paper(time.time() - start_paper_time, 0)

        # 3. Contradiction Detection
        progress_tracker.update_status("contradiction", "Detecting contradictions")
        progress_tracker.add_log("Running Contradiction Agent...")
        try:
            # Query Neo4j for claims matching the processed papers to focus checks
            from graph.neo4j_client import run_query
            processed_arxiv_ids = [p["arxiv_id"] for p in papers]
            res = run_query("""
                MATCH (c:Claim)-[:EXTRACTED_FROM]->(p:Paper)
                WHERE p.arxiv_id IN $arxiv_ids
                RETURN elementId(c) AS claim_id
            """, {"arxiv_ids": processed_arxiv_ids})
            new_claim_ids = [r["claim_id"] for r in res] if res else []
            progress_tracker.add_log(f"Found {len(new_claim_ids)} newly ingested claims. Running targeted contradiction checks...")

            contras_found = run_contradiction_detection(limit_to_claim_ids=new_claim_ids)
            progress_tracker.add_log(f"Contradiction Agent complete. Found {contras_found} contradictions.")
        except Exception as e:
            progress_tracker.add_log(f"Error during contradiction detection: {str(e)}")
            contras_found = 0

        # 4. Recalculate confidence
        progress_tracker.update_status("confidence", "Recalculating confidence scores")
        progress_tracker.add_log("Running Confidence Propagation Agent...")
        try:
            summary = recalculate_all()
            progress_tracker.add_log(f"Confidence propagation complete. Updated {summary.get('total_updated', 0)} claims.")
        except Exception as e:
            progress_tracker.add_log(f"Error during confidence recalculation: {str(e)}")

        # Complete
        progress_tracker.complete(contras_found)

    except Exception as e:
        logger.exception("Custom ingestion pipeline failed")
        progress_tracker.fail(str(e))


if __name__ == "__main__":
    # Standalone: run immediately, then stay on schedule
    trigger_now()
    start_scheduler()
    print("Scheduler running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        stop_scheduler()