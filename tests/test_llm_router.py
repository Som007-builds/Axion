"""
LLM router tests: error classification, retry/fallback policy, cooldowns, and
the Gemini generation config.

All provider callers are stubbed — nothing here touches a real API.
"""
from unittest.mock import patch

import pytest

import llm
from llm import (
    _is_rate_limit,
    _is_transient,
    call_llm,
    reset_cooldowns,
)


class ProviderError(Exception):
    """Stand-in for a provider SDK error, with a controllable message."""


# ─── Error classification ─────────────────────────────────────────────────────

class TestErrorClassification:
    @pytest.mark.parametrize("message", [
        "429 Too Many Requests",
        "rate_limit_exceeded",
        "Rate limit reached for gpt-oss-20b",
        "RESOURCE_EXHAUSTED: quota exceeded",
        "You exceeded your current quota",
    ])
    def test_rate_limits_detected(self, message):
        assert _is_rate_limit(ProviderError(message)) is True

    @pytest.mark.parametrize("message", [
        "model `llama-3.1-8b-instant` does not exist",
        "invalid api key",
        "401 Unauthorized",
    ])
    def test_permanent_errors_are_not_rate_limits(self, message):
        assert _is_rate_limit(ProviderError(message)) is False
        assert _is_transient(ProviderError(message)) is False

    @pytest.mark.parametrize("message", [
        "503 UNAVAILABLE. This model is currently experiencing high demand.",
        "502 Bad Gateway",
        "504 Deadline Exceeded",
        "request timed out",
        "Connection reset by peer",
    ])
    def test_transient_errors_detected(self, message):
        assert _is_transient(ProviderError(message)) is True

    def test_404_is_not_transient(self):
        """A retired model name must not be retried — it never comes back."""
        exc = ProviderError("404 NOT_FOUND. This model is no longer available")
        assert _is_transient(exc) is False
        assert _is_rate_limit(exc) is False


# ─── Retry / fallback policy ──────────────────────────────────────────────────

@pytest.fixture
def stub_providers():
    """Install two controllable providers and a chain that uses both."""
    calls: list[str] = []

    def install(primary, secondary):
        def groq(prompt, max_tokens):
            calls.append("groq")
            return primary()

        def gemini(prompt, max_tokens):
            calls.append("gemini")
            return secondary()

        return patch.object(llm.config, "LLM_PROVIDER", "groq"), \
            patch.object(llm, "LLM_PROVIDER_CHAIN", ["groq", "gemini"]), \
            patch.dict(llm._PROVIDERS, {"groq": groq, "gemini": gemini})

    return calls, install


class TestFallbackPolicy:
    def test_transient_error_is_retried_not_abandoned(self, stub_providers):
        """A 503 from the primary must not end the chain immediately."""
        calls, install = stub_providers
        attempts = {"n": 0}

        def flaky():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ProviderError("503 UNAVAILABLE: high demand")
            return "recovered"

        def unused():
            raise AssertionError("Gemini should not be reached")

        a, b, c = install(flaky, unused)
        with a, b, c, patch("llm.time.sleep"):
            assert call_llm("prompt") == "recovered"

        assert attempts["n"] == 3
        assert "gemini" not in calls

    def test_transient_errors_exhaust_then_fall_back(self, stub_providers):
        calls, install = stub_providers

        def always_503():
            raise ProviderError("503 Service Unavailable")

        a, b, c = install(always_503, lambda: "gemini answer")
        with a, b, c, patch("llm.time.sleep") as sleep:
            result = call_llm("prompt", retries=2)

        assert result == "gemini answer"
        assert calls == ["groq", "groq", "gemini"]
        # Short transient schedule, not the long rate-limit one.
        assert sleep.call_count == 1

    def test_permanent_error_skips_provider_immediately(self, stub_providers):
        calls, install = stub_providers

        def dead():
            raise ProviderError("model not found")

        a, b, c = install(dead, lambda: "gemini answer")
        with a, b, c, patch("llm.time.sleep") as sleep:
            result = call_llm("prompt", retries=5)

        assert result == "gemini answer"
        assert calls == ["groq", "gemini"]
        sleep.assert_not_called()


# ─── Cooldowns ────────────────────────────────────────────────────────────────

class TestCooldown:
    def test_failed_provider_is_skipped_on_later_calls(self, stub_providers):
        calls, install = stub_providers

        def dead():
            raise ProviderError("model not found")

        a, b, c = install(dead, lambda: "gemini answer")
        with a, b, c:
            assert call_llm("first") == "gemini answer"
            assert call_llm("second") == "gemini answer"

        # Groq is tried once, then taken out of rotation.
        assert calls == ["groq", "gemini", "gemini"]

    def test_cooldown_expiry_puts_the_provider_back(self, stub_providers):
        calls, install = stub_providers

        def dead():
            raise ProviderError("model not found")

        a, b, c = install(dead, lambda: "gemini answer")
        with a, b, c:
            call_llm("first")

        # Simulate the cooldown window elapsing.
        with patch.object(llm, "LLM_PROVIDER_COOLDOWN_SECONDS", 0):
            llm.reset_cooldowns()

        with a, b, c:
            call_llm("second")

        assert calls == ["groq", "gemini", "groq", "gemini"]

    def test_all_providers_cooling_still_attempts_the_chain(self, stub_providers):
        """Never fail fast just because everything is in cooldown."""
        calls, install = stub_providers

        def dead():
            raise ProviderError("model not found")

        a, b, c = install(dead, dead)
        with a, b, c:
            with pytest.raises(Exception, match="All LLM providers exhausted"):
                call_llm("first")
            with pytest.raises(Exception, match="All LLM providers exhausted"):
                call_llm("second")

        # Both were attempted on the second call rather than skipped outright.
        assert calls == ["groq", "gemini", "groq", "gemini"]

    def test_success_resets_nothing(self, stub_providers):
        calls, install = stub_providers
        a, b, c = install(lambda: "fine", lambda: "fine")
        with a, b, c:
            assert call_llm("one") == "fine"
            assert call_llm("two") == "fine"

        assert calls == ["groq", "groq"]

    def test_reset_cooldowns_clears_state(self):
        llm._start_cooldown("groq", "test")
        assert llm._in_cooldown("groq") is True
        reset_cooldowns()
        assert llm._in_cooldown("groq") is False


# ─── Provider-specific configuration ──────────────────────────────────────────

def _fake_genai_module(response_factory):
    """
    Build a stand-in for `google.genai` that records the config it receives.

    `_call_gemini` does `from google import genai` and `_gemini_generation_config`
    does `from google.genai import types`, so both the attribute on the `google`
    package and the submodule entry have to be patched.
    """
    captured = {}

    class ThinkingConfig:
        def __init__(self, thinking_budget=None):
            self.thinking_budget = thinking_budget

    class GenerateContentConfig:
        def __init__(self, **kwargs):
            self.max_output_tokens = kwargs.get("max_output_tokens")
            self.thinking_config = kwargs.get("thinking_config")

    class _Models:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return response_factory()

    class Client:
        def __init__(self, api_key=None):
            self.models = _Models()

    module = type("fake_genai", (), {
        "Client": Client,
        "types": type("fake_types", (), {
            "ThinkingConfig": ThinkingConfig,
            "GenerateContentConfig": GenerateContentConfig,
        }),
    })
    return module, captured


def _fake_response(text, finish_reason=None):
    return type("R", (), {
        "text": text,
        "candidates": ([type("C", (), {"finish_reason": finish_reason})()]
                       if finish_reason else []),
    })()


class TestGeminiConfig:
    def test_thinking_is_disabled_on_modern_models(self):
        """3.x burns ~120 hidden tokens per call; our prompts want short JSON."""
        with patch.object(llm, "GEMINI_MODEL", "gemini-3.8-flash"), \
             patch.object(llm, "GEMINI_THINKING_BUDGET", 0):
            config = llm._gemini_generation_config(1024)

        assert config.max_output_tokens == 1024
        assert config.thinking_config.thinking_budget == 0

    def test_older_models_do_not_get_thinking_config(self):
        """2.0/1.5 reject thinking_config, so it must be omitted for them."""
        for model in ("gemini-2.0-flash", "gemini-1.5-pro"):
            with patch.object(llm, "GEMINI_MODEL", model):
                config = llm._gemini_generation_config(256)
            assert config.thinking_config is None

    def test_gemini_token_budget_is_forwarded(self):
        """The budget used to be ignored entirely (no max_output_tokens)."""
        import google

        module, captured = _fake_genai_module(lambda: _fake_response(" answer "))
        with patch.dict("sys.modules", {"google.genai": module}), \
             patch.object(google, "genai", module, create=True), \
             patch.object(llm, "GEMINI_MODEL", "gemini-3.8-flash"):
            result = llm._call_gemini("prompt", 321)

        assert result == "answer"
        assert captured["config"].max_output_tokens == 321
        assert captured["config"].thinking_config.thinking_budget == 0

    def test_empty_gemini_response_raises_a_clear_error(self):
        """A thought-only completion must surface as a provider failure."""
        import google

        module, _ = _fake_genai_module(
            lambda: _fake_response(None, finish_reason="MAX_TOKENS")
        )
        with patch.dict("sys.modules", {"google.genai": module}), \
             patch.object(google, "genai", module, create=True):
            with pytest.raises(ValueError, match="returned no text"):
                llm._call_gemini("prompt", 64)
