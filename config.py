import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

# ─── LLM ─────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-20250514"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

# Output tokens Gemini 2.5+/3.x may spend on hidden "thinking" before answering.
# Measured 2026-10-17 on gemini-3.8-flash: ~110-130 tokens even for a
# two-character reply, which is enough to consume a small max_tokens budget and
# return empty text. Axion's prompts ask for short JSON, so thinking is waste.
# 0 disables it; -1 lets the model decide.
GEMINI_THINKING_BUDGET = int(os.getenv("GEMINI_THINKING_BUDGET", "0"))

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = "openai/gpt-oss-20b"

# Primary provider: "groq", "gemini", or "claude"
LLM_PROVIDER = "groq"

# Provider fallback chain — tried in order when the primary is rate-limited.
# Set to a single-element list to disable fallback.
LLM_PROVIDER_CHAIN = ["groq", "gemini"]

# After a provider fails hard (quota spent, decommissioned model, bad key), skip
# it for this many seconds instead of paying the full retry schedule on every
# subsequent call. Free-tier Groq caps are daily, so retrying it 5 times (~185s)
# per call just makes every request slow.
LLM_PROVIDER_COOLDOWN_SECONDS = int(os.getenv("LLM_PROVIDER_COOLDOWN_SECONDS", "300"))

# LLM cache: set to True to enable in-process response caching (saves API calls
# for repeated identical prompts, e.g. during dev / repeated contradiction checks)
LLM_CACHE_ENABLED = os.getenv("LLM_CACHE_ENABLED", "false").lower() == "true"

# ─── Paths ───────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "db" / "axion.db"
PAPERS_DIR = DATA_DIR / "papers"
CHROMA_DIR = DATA_DIR / "db" / "chroma"

# ─── Embeddings ──────────────────────────────────────────────
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100

# ─── Agent settings ──────────────────────────────────────────
MAX_CLAIMS_PER_PAPER = 8

# Maximum ChromaDB distance (1 − cosine similarity) for a candidate pair to
# reach the LLM judgment stage.
#
# Measured on the live 2,389-claim index (2026-10-17): nearest-neighbour
# distances run 0.00–0.63 (p50 0.33), so the historical gate of 0.95 admitted
# **100%** of neighbours — every claim was judged against 8 arbitrary
# neighbours regardless of relevance, which is a root cause of the ~1.8%
# audited contradiction precision. 0.35 ≈ cosine similarity 0.65: it keeps the
# nearest neighbour for ~96% of claims while dropping ~45% of the least
# comparable pairs (and the LLM calls they would have cost).
CONTRADICTION_MAX_DISTANCE = float(os.getenv("CONTRADICTION_MAX_DISTANCE", "0.35"))

# Deprecated alias kept so older configs/tests keep importing successfully.
CONTRADICTION_THRESHOLD = CONTRADICTION_MAX_DISTANCE

# ─── Neo4j ───────────────────────────────────────────────────
# Keep these defaults in sync with docker-compose.yml (host port 7887,
# container name axion_neo4j) so a fresh `docker compose up` works.
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7887")
NEO4J_USER = os.getenv("NEO4J_USERNAME", os.getenv("NEO4J_USER", "neo4j"))
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_CONTAINER_NAME = os.getenv("NEO4J_CONTAINER_NAME", "axion_neo4j")

# ─── API / CORS ──────────────────────────────────────────────
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")

# ─── Scheduler ───────────────────────────────────────────────
# Set SCHEDULER_ENABLED=true to run the periodic ingestion scheduler inside
# the API process. Requires a SINGLE API worker (apscheduler is in-process),
# e.g. `uvicorn api.main:app --workers 1`.
SCHEDULER_ENABLED = os.getenv("SCHEDULER_ENABLED", "false").lower() == "true"
SCHEDULER_INTERVAL_HOURS = int(os.getenv("SCHEDULER_INTERVAL_HOURS", "6"))
SCHEDULER_PAPERS_PER_RUN = int(os.getenv("SCHEDULER_PAPERS_PER_RUN", "5"))
SCHEDULER_TOPICS = [
    "chain of thought prompting LLM",
    "in-context learning large language models",
    "LLM reasoning benchmark evaluation",
    "instruction tuning language models",
    "RLHF reinforcement learning human feedback"
]
# Narrow topics surface better papers. Add or change as the graph grows.

# ─── Job queue ───────────────────────────────────────────────
# Redis URL for the durable job queue (RQ) and cross-process job/progress
# state. When empty the API falls back to an in-process thread backend: the
# same job API, but jobs are lost on restart and state is per-process.
# docker-compose sets this to redis://redis:6379/0.
REDIS_URL = os.getenv("REDIS_URL", "")

# How long finished job records (and their results) are kept, in seconds.
JOB_TTL_SECONDS = int(os.getenv("JOB_TTL_SECONDS", "86400"))

# Maximum wall-clock time for a single queued job, in seconds. Multi-paper
# ingestion and multi-iteration research queries are both slow; 30 minutes is
# generous without letting a wedged job hold a worker forever.
JOB_TIMEOUT_SECONDS = int(os.getenv("JOB_TIMEOUT_SECONDS", "1800"))

# ─── Security ────────────────────────────────────────────────
# Shared secret required by write/compute endpoints: POST /api/query,
# POST /api/experiments/{id}/design, POST /api/confidence/recalculate and the
# ingestion triggers. The frontend sends it from its server-side proxy as the
# `X-API-Key` header, so it never reaches the browser bundle.
# Empty ⇒ those endpoints fail closed (503), never open to anonymous callers.
API_KEY = os.getenv("AXION_API_KEY", "")

# Legacy shared secret for the ingestion trigger endpoints. Still accepted
# (header `X-Trigger-Secret`) for backwards compatibility; prefer AXION_API_KEY.
TRIGGER_SECRET = os.getenv("TRIGGER_SECRET", "")