# llm.py
"""
Resilient LLM call router for AXION.

Phase 3 upgrades:
  - Exponential backoff with jitter on rate limits (replaces fixed 60s/120s/180s sleep)
  - Provider fallback chain: if primary is exhausted, try next provider
  - Optional in-process cache (LLM_CACHE_ENABLED=true in .env)
  - Per-call timing via LLMCallTimer
  - Metrics integration (rate_limit_events, call latency)
  - Improved rate-limit detection covering all three provider error formats
"""

from __future__ import annotations

import logging
import random
import threading
import time

import config
from config import (
    ANTHROPIC_API_KEY, CLAUDE_MODEL,
    GEMINI_API_KEY, GEMINI_MODEL, GEMINI_THINKING_BUDGET,
    GROQ_API_KEY, GROQ_MODEL,
    LLM_PROVIDER_CHAIN, LLM_CACHE_ENABLED, LLM_PROVIDER_COOLDOWN_SECONDS,
)

logger = logging.getLogger(__name__)

# Exponential back-off: attempt index → seconds to wait before retry.
# Jitter of ±3 seconds is added per attempt to avoid thundering-herd.
_RETRY_DELAYS = [5, 15, 45, 120, 300]

# Transient server errors clear quickly, so they get a shorter schedule.
_TRANSIENT_RETRY_DELAYS = [2, 5, 10]

# Providers that just failed hard (quota spent, decommissioned model, bad key)
# are skipped for a cooldown window.
#
# Why: exhausting the retry schedule above costs ~185s per call. A provider on a
# free-tier daily cap would therefore add ~3 minutes to *every* LLM call in the
# application, for the rest of the day, even though the fallback provider is
# healthy. Measured live on 2026-10-17: with Groq capped, a 286-pair eval run
# would have taken hours instead of minutes.
_cooldown_until: dict[str, float] = {}
_cooldown_lock = threading.Lock()


def _in_cooldown(provider: str) -> bool:
    with _cooldown_lock:
        until = _cooldown_until.get(provider, 0.0)
    return time.monotonic() < until


def _start_cooldown(provider: str, reason: str) -> None:
    """Skip `provider` for the cooldown window after a hard failure."""
    with _cooldown_lock:
        _cooldown_until[provider] = time.monotonic() + LLM_PROVIDER_COOLDOWN_SECONDS
    logger.warning(
        f"[llm] [{provider}] taken out of rotation for "
        f"{LLM_PROVIDER_COOLDOWN_SECONDS}s ({reason})."
    )


def reset_cooldowns() -> None:
    """Clear the cooldown state (tests, and after a config/key change)."""
    with _cooldown_lock:
        _cooldown_until.clear()


# ─── Rate-limit detection ─────────────────────────────────────────────────────

def _is_rate_limit(exc: Exception) -> bool:
    """Return True if exception looks like a provider rate-limit error."""
    msg = str(exc).lower()
    return any(
        kw in msg for kw in (
            "rate_limit", "rate limit", "ratelimit",
            "429", "too many requests",
            "quota", "resource_exhausted",
        )
    )


def _is_transient(exc: Exception) -> bool:
    """
    Return True for server-side hiccups that are worth retrying.

    Providers return these routinely under load (e.g. Gemini
    "503 UNAVAILABLE: this model is currently experiencing high demand").
    Treating them as permanent ended the whole fallback chain on a single
    unlucky response.
    """
    msg = str(exc).lower()
    return any(
        kw in msg for kw in (
            "503", "502", "504", "500",
            "unavailable", "overloaded", "internal error", "internal server",
            "timeout", "timed out", "connection reset", "connection aborted",
            "service unavailable", "try again later",
        )
    )


# ─── Per-provider call implementations ───────────────────────────────────────

def _call_groq(prompt: str, max_tokens: int) -> str:
    from groq import Groq
    client = Groq(api_key=GROQ_API_KEY)
    kwargs = {
        "model": GROQ_MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    # Reasoning models (openai/gpt-oss-*, qwen3-*) otherwise spend the whole
    # max_tokens budget on hidden reasoning and can return empty content.
    if "gpt-oss" in GROQ_MODEL or "qwen3" in GROQ_MODEL:
        kwargs["reasoning_effort"] = "low"
    response = client.chat.completions.create(**kwargs)
    return (response.choices[0].message.content or "").strip()


def _call_gemini(prompt: str, max_tokens: int) -> str:
    from google import genai

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=_gemini_generation_config(max_tokens),
    )
    if not response.text:
        # Blocked or thought-only completion. Raise instead of letting
        # `None.strip()` escape as an AttributeError so the fallback chain
        # treats this as a provider failure.
        reason = None
        if response.candidates:
            reason = getattr(response.candidates[0], "finish_reason", None)
        raise ValueError(f"[gemini] returned no text (finish_reason={reason})")
    return response.text.strip()


def _gemini_generation_config(max_tokens: int):
    """Build the Gemini generation config for a short-answer call."""
    from google.genai import types

    kwargs = {"max_output_tokens": max_tokens}
    if not GEMINI_MODEL.startswith(("gemini-2.0", "gemini-1.5")):
        # 2.5+/3.x models support thinking control; 2.0 and older reject it.
        kwargs["thinking_config"] = types.ThinkingConfig(
            thinking_budget=GEMINI_THINKING_BUDGET
        )
    return types.GenerateContentConfig(**kwargs)


def _call_claude(prompt: str, max_tokens: int) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


_PROVIDERS = {
    "groq":   _call_groq,
    "gemini": _call_gemini,
    "claude": _call_claude,
}


# ─── Main entry point ─────────────────────────────────────────────────────────

def call_llm(
    prompt: str,
    max_tokens: int = 1500,
    retries: int = 5,
    context: str = "",
) -> str:
    """
    Route a prompt through the configured LLM provider chain.

    Args:
        prompt:     The prompt string.
        max_tokens: Maximum tokens for the response.
        retries:    How many times to retry per provider before moving to the next.
        context:    Optional tag for log messages (e.g. "reader.extract_claims").

    Returns:
        The LLM response as a stripped string.

    Raises:
        Exception: When all providers in the chain are exhausted after retries.
    """
    # ── Optional cache lookup ─────────────────────────────────────────────────
    if LLM_CACHE_ENABLED:
        from utils.llm_cache import get_cached, set_cached
        primary = config.LLM_PROVIDER
        cached = get_cached(primary, prompt)
        if cached is not None:
            return cached

    # ── Metrics import (lazy, won't fail if metrics module unavailable) ───────
    try:
        from utils.metrics import metrics as _metrics
    except Exception:
        _metrics = None

    tag = f"[llm:{context}]" if context else "[llm]"

    # Build the provider list: primary first, then remaining from chain
    primary = config.LLM_PROVIDER
    chain = list(LLM_PROVIDER_CHAIN) if LLM_PROVIDER_CHAIN else [primary]
    if primary not in chain:
        chain.insert(0, primary)

    last_error: Exception | None = None

    # Skip providers that are in a post-failure cooldown — unless that would
    # leave nothing to try, in which case run the chain as-is (better a slow
    # attempt than a guaranteed failure).
    active_chain = [p for p in chain if not _in_cooldown(p)]
    if not active_chain:
        active_chain = chain
    elif len(active_chain) < len(chain):
        skipped = [p for p in chain if p not in active_chain]
        logger.info(f"{tag} Skipping {skipped} (in cooldown after a recent failure).")

    # ── Provider fallback loop ────────────────────────────────────────────────
    for provider in active_chain:
        caller = _PROVIDERS.get(provider)
        if caller is None:
            logger.warning(f"{tag} Unknown provider '{provider}', skipping.")
            continue

        for attempt in range(retries):
            t0 = time.perf_counter()
            try:
                result = caller(prompt, max_tokens)
                if not result or not result.strip():
                    # An empty completion is a provider failure, not a valid
                    # answer — surface it so the fallback chain can proceed.
                    raise ValueError(f"[{provider}] returned an empty response")
                elapsed_ms = (time.perf_counter() - t0) * 1000

                logger.debug(
                    f"{tag} [{provider}] call completed in {elapsed_ms:.0f}ms"
                )

                if _metrics:
                    _metrics.record_llm_call(
                        provider=provider,
                        duration_ms=elapsed_ms,
                        success=True,
                    )

                # ── Cache store ───────────────────────────────────────────────
                if LLM_CACHE_ENABLED:
                    set_cached(provider, prompt, result)

                return result

            except Exception as exc:
                elapsed_ms = (time.perf_counter() - t0) * 1000

                rate_limited = _is_rate_limit(exc)
                # Server-side hiccups (503/502/504, timeouts, dropped
                # connections) are retried on a short back-off: they usually
                # clear in seconds, and treating them as permanent used to fail
                # the whole chain on a single "model is experiencing high
                # demand" response.
                transient = (not rate_limited) and _is_transient(exc)

                if rate_limited or transient:
                    if rate_limited and _metrics:
                        _metrics.record_rate_limit(provider)

                    if attempt < retries - 1:
                        schedule = _RETRY_DELAYS if rate_limited else _TRANSIENT_RETRY_DELAYS
                        base_delay = schedule[min(attempt, len(schedule) - 1)]
                        jitter = random.uniform(-3.0, 3.0)
                        delay = max(1.0, base_delay + jitter)
                        logger.warning(
                            f"{tag} [{provider}] "
                            f"{'Rate-limited' if rate_limited else 'Temporarily unavailable'}"
                            f" ({exc}). Retry {attempt + 1}/{retries} in {delay:.0f}s…"
                        )
                        time.sleep(delay)
                        continue

                    reason = "rate limit" if rate_limited else "provider unavailable"
                    logger.warning(
                        f"{tag} [{provider}] retries exhausted after {retries} attempts "
                        f"({reason}). Trying next provider."
                    )
                    if _metrics:
                        _metrics.record_llm_call(
                            provider=provider,
                            duration_ms=elapsed_ms,
                            success=False,
                            rate_limited=rate_limited,
                        )
                    last_error = exc
                    _start_cooldown(provider, reason)
                    break   # move to next provider

                else:
                    # Permanent error (dead model name, bad key, malformed
                    # request…): this provider is unusable right now, so fall
                    # through to the next provider instead of failing the whole
                    # chain — one stale model name must not take down every
                    # LLM call in the application.
                    logger.error(
                        f"{tag} [{provider}] Non-retriable error: {exc}"
                    )
                    if _metrics:
                        _metrics.record_llm_call(
                            provider=provider,
                            duration_ms=elapsed_ms,
                            success=False,
                        )
                    last_error = exc
                    _start_cooldown(provider, "non-retriable error")
                    break   # move to next provider

    raise Exception(
        f"All LLM providers exhausted after retries. "
        f"Chain tried: {active_chain}. "
        f"Consider checking API keys or rate limit quotas."
    ) from last_error