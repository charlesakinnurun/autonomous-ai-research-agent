"""Smoke test: the scaffold is installable and the required config exists.

This is deliberately not an eval. The replay-only 5-question smoke eval replaces
this in Phase 5.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import research_agent

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.smoke
def test_package_imports() -> None:
    assert research_agent.__version__


@pytest.mark.smoke
def test_env_example_has_no_secret_values() -> None:
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "GROQ_API_KEY=" in env_example
    assert "GEMINI_API_KEY=" in env_example
    for line in env_example.splitlines():
        if line.startswith(("GROQ_API_KEY=", "GEMINI_API_KEY=", "OPENROUTER_API_KEY=")):
            _, value = line.split("=", 1)
            assert value == "", f"secret-looking value in .env.example: {line}"
