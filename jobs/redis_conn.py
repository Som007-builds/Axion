# jobs/redis_conn.py
"""Shared Redis connection helper.

Redis is optional: everything that uses it must degrade gracefully when
`REDIS_URL` is unset or the server is unreachable, because local development
and the offline test suite run without Redis.
"""
from __future__ import annotations

import logging
import threading

import config

logger = logging.getLogger(__name__)

_client = None
_lock = threading.Lock()
_warned = False


def is_configured() -> bool:
    """True when a Redis URL is configured (does not test reachability)."""
    return bool(config.REDIS_URL)


def get_redis():
    """Return a shared Redis client, or ``None`` when unavailable.

    Never raises: a missing `redis` package or an unreachable server both
    return ``None`` so callers can fall back to in-process behaviour.

    The connection deliberately runs in bytes mode (``decode_responses=False``):
    RQ calls ``.decode()`` on the values it reads back, so a decoding client
    crashes its worker with ``'str' object has no attribute 'decode'`` on the
    very first job. Callers that want text decode explicitly.
    """
    global _client, _warned
    if not config.REDIS_URL:
        return None

    with _lock:
        if _client is not None:
            return _client
        try:
            import redis  # imported lazily so the dependency stays optional

            client = redis.Redis.from_url(
                config.REDIS_URL,
                socket_connect_timeout=3,
                socket_timeout=3,
                decode_responses=False,
            )
            client.ping()
            _client = client
            logger.info("Job queue: connected to Redis at %s", _safe(config.REDIS_URL))
            return _client
        except Exception as exc:  # noqa: BLE001 - any failure means "no Redis"
            if not _warned:
                logger.warning(
                    "Job queue: Redis unavailable (%s) — falling back to the "
                    "in-process backend. Jobs will not survive a restart.",
                    exc,
                )
                _warned = True
            return None


def reset() -> None:
    """Drop the cached client (used by tests and after a failed connection)."""
    global _client, _warned
    with _lock:
        _client = None
        _warned = False


def _safe(url: str) -> str:
    """Render a Redis URL without any embedded password."""
    if "@" in url:
        scheme, _, host = url.partition("://")
        return f"{scheme}://***@{host.split('@', 1)[1]}"
    return url
