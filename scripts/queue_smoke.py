# scripts/queue_smoke.py
"""End-to-end smoke test for the durable job queue.

Verifies the deployed stack, not the code: that job polling is credentialled,
that `POST /api/query` returns `202` with a job id, and that a **separate worker
process** picks the job up (status leaves `queued`).

    python scripts/queue_smoke.py

Reads the API key from `AXION_API_KEY` (or the repo-root `.env`) and the base URL
from `AXION_API_BASE` (default `http://localhost:8000`). The job it submits is a
real query, so it consumes LLM quota; stop after the `running` transition if you
only care about the plumbing.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API = os.environ.get("AXION_API_BASE", "http://localhost:8000")

# The transition poll: how long to wait for the worker to claim the job.
CLAIM_TIMEOUT_SECONDS = 90
POLL_INTERVAL_SECONDS = 2


def load_key() -> str:
    key = os.environ.get("AXION_API_KEY")
    if key:
        return key
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("AXION_API_KEY="):
                key = line.split("=", 1)[1].strip()
                if key:
                    return key
    raise SystemExit(
        "AXION_API_KEY is not set and could not be read from .env — "
        "export it or run this from the repository root."
    )


def request(method: str, path: str, body: dict | None = None, key: str | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{API}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if key:
        req.add_header("X-API-Key", key)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def main() -> int:
    key = load_key()
    failures: list[str] = []

    print("1. job polling is credentialled")
    status, body = request("GET", "/api/jobs/smoke-does-not-exist")
    print(f"   without key -> {status} {body.get('detail', body)}")
    if status != 401:
        failures.append(f"expected 401 without a key, got {status}")

    status, body = request("GET", "/api/jobs/smoke-does-not-exist", key=key)
    print(f"   with key    -> {status} {body.get('detail', body)}")
    if status != 404:
        failures.append(f"expected 404 for an unknown job, got {status}")

    print("\n2. submit a query (expect 202 + job id)")
    status, body = request("POST", "/api/query", {"question": "queue smoke test"}, key=key)
    print(f"   POST /api/query -> {status} {body}")
    if status != 202 or "job_id" not in body:
        print("\nRESULT: FAIL — the API did not accept the job.")
        return 1
    job_id = body["job_id"]
    print(f"   backend: {body.get('backend')}")

    print(f"\n3. wait up to {CLAIM_TIMEOUT_SECONDS}s for the worker to claim it")
    seen: list[str] = []
    deadline = time.monotonic() + CLAIM_TIMEOUT_SECONDS
    record: dict = {}
    while time.monotonic() < deadline:
        status, record = request("GET", f"/api/jobs/{job_id}", key=key)
        state = record.get("status")
        if not seen or seen[-1] != state:
            seen.append(state)
            print(f"   +{CLAIM_TIMEOUT_SECONDS - int(deadline - time.monotonic()):>3}s  {state}")
        if state in ("running", "completed", "failed"):
            break
        time.sleep(POLL_INTERVAL_SECONDS)

    print(f"   transitions observed: {seen}")
    if "running" in seen or "completed" in seen:
        print("   the worker claimed a job created by the API process")
    else:
        failures.append(
            "the job never left 'queued' — is the worker running? "
            "docker compose logs worker"
        )

    print("\n4. latest job record")
    print(f"   {json.dumps({k: v for k, v in record.items() if k != 'result'})}")
    if any(field in record for field in ("_payload",)):
        failures.append("the public job record leaked a private field")

    print()
    if failures:
        for item in failures:
            print(f"RESULT: FAIL — {item}")
        return 1
    print("RESULT: OK — the queue works end to end.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
