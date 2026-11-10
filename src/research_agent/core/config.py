"""Compatibility re-exports.

The canonical settings module is :mod:`research_agent.config`. This module exists
so internal code can keep a single ``core`` import surface without creating a
second, divergent ``Settings`` class.
"""

from research_agent.config import LLMMode, Settings, get_settings
from research_agent.core.runtime import configure_windows_event_loop, load_yaml

__all__ = ["LLMMode", "Settings", "configure_windows_event_loop", "get_settings", "load_yaml"]
