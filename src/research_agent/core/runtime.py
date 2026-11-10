"""Small runtime helpers shared by entry points.

Keep this module dependency-free so tests and scripts can import it cheaply.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML mapping, failing loudly on malformed/non-mapping files."""
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"config file must contain a mapping: {path}")
    return raw


def configure_windows_event_loop() -> None:
    """psycopg async cannot use Windows' default ProactorEventLoop.

    Call this at every asyncio entry point (API, worker, scripts, tests).
    """
    if sys.platform == "win32":
        import asyncio

        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
