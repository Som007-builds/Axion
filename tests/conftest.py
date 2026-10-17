"""
Shared pytest configuration.

The LLM router keeps process-global state (providers taken out of rotation
after a hard failure). That state must not leak between tests, or a test that
deliberately breaks the primary provider would silently change which provider
later tests exercise.
"""
import pytest


@pytest.fixture(autouse=True)
def _reset_llm_cooldowns():
    import llm

    llm.reset_cooldowns()
    yield
    llm.reset_cooldowns()
