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
import time

import config
from config import (
    ANTHROPIC_API_KEY, CLAUDE_MODEL,
    GEMINI_API_KEY, GEMINI_MODEL,
    GROQ_API_KEY, GROQ_MODEL,
    LLM_PROVIDER_CHAIN, LLM_CACHE_ENABLED,
)

logger = logging.getLogger(__name__)

# Exponential back-off: attempt index → seconds to wait before retry.
# Jitter of ±3 seconds is added per attempt to avoid thundering-herd.
_RETRY_DELAYS = [5, 15, 45, 120, 300]


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
    )
    return response.text.strip()


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

    # ── Provider fallback loop ────────────────────────────────────────────────
    for provider in chain:
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

                if _is_rate_limit(exc):
                    if _metrics:
                        _metrics.record_rate_limit(provider)

                    if attempt < retries - 1:
                        base_delay = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
                        jitter = random.uniform(-3.0, 3.0)
                        delay = max(1.0, base_delay + jitter)
                        logger.warning(
                            f"{tag} [{provider}] Rate-limited. "
                            f"Retry {attempt + 1}/{retries} in {delay:.0f}s…"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        logger.warning(
                            f"{tag} [{provider}] Rate-limit retries exhausted "
                            f"({retries} attempts). Trying next provider."
                        )
                        if _metrics:
                            _metrics.record_llm_call(
                                provider=provider,
                                duration_ms=elapsed_ms,
                                success=False,
                                rate_limited=True,
                            )
                        break   # move to next provider

                else:
                    # Non-rate-limit error (dead model name, bad key, malformed
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
                    break   # move to next provider

    raise Exception(
        f"All LLM providers exhausted after retries. "
        f"Chain tried: {chain}. "
        f"Consider checking API keys or rate limit quotas."
    ) from last_error