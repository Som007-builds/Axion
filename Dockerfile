# Dockerfile — Axion backend (FastAPI + agents)
#
# Build:  docker build -t axion-api .
# Run:    docker run --rm -p 8000:8000 --env-file .env axion-api
# Or use: docker compose up --build
#
# The API needs a reachable Neo4j (bolt) and the ChromaDB files under ./data.
# In docker-compose both are provided; NEO4J_URI is overridden to the compose
# service name.

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface

WORKDIR /app

# Minimal system deps. PyMuPDF ships manylinux wheels; no compiler needed here.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install CPU-only PyTorch FIRST. sentence-transformers depends on torch, and
# the default PyPI wheel on Linux drags in ~2.5 GB of CUDA libraries that this
# service never uses. Installing the CPU wheel up front keeps the image usable.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Liveness only (always 200 while the process serves). Datastore outages are
# reported by /api/health and must not cause container restarts.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz', timeout=4).status==200 else 1)"

# Single worker: the in-process ingestion scheduler and the in-memory metrics
# tracker are not multi-process safe. Long-running work (ingestion, research
# queries) is queued and executed by the separate `worker` service; see
# `jobs/worker.py` and docker-compose.yml.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
