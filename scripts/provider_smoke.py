"""Verify provider keys, model IDs, and JSON mode.

Usage:
    uv run python scripts/provider_smoke.py --live
    uv run python scripts/provider_smoke.py --live --provider groq

This script makes live calls and consumes free-tier quota. It is not run in CI.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Allow running as a script without installing the package first.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from research_agent.config import get_settings
from research_agent.core.config import configure_windows_event_loop
from research_agent.llm.client import LLMClient
from research_agent.llm.provider_config import default_providers_config
from research_agent.models.common import Role
from research_agent.models.tools import LLMMessage, LLMRequest


async def run(provider_names: list[str], live: bool) -> int:
    if not live:
        print("Refusing to make live calls without --live", file=sys.stderr)
        return 2
    settings = get_settings()
    config = default_providers_config(settings)
    selected = provider_names or list(config.enabled())
    failures = 0
    for name in selected:
        provider = config.providers.get(name)
        if provider is None or not provider.enabled:
            print(f"{name}: not enabled")
            continue
        client = LLMClient(provider_name=name, config=provider, settings=settings)
        request = LLMRequest(
            model="fast",
            messages=[
                LLMMessage(
                    role=Role.SYSTEM,
                    content="You are a health check. Reply with a single JSON object.",
                ),
                LLMMessage(role=Role.USER, content='Return {"ok": true}.'),
            ],
            temperature=0.0,
            max_tokens=32,
            response_format="json_object" if provider.capabilities.json_mode else None,
        )
        try:
            response = await client.chat(request)
            print(
                f"{name}: ok model={response.model} tokens={response.usage.total_tokens} "
                f"latency_ms={response.latency_ms:.0f} content={response.content[:80]!r}"
            )
        except Exception as exc:
            failures += 1
            print(f"{name}: FAILED {type(exc).__name__}: {exc}", file=sys.stderr)
        finally:
            await client.aclose()
    return 1 if failures else 0


def main() -> int:
    configure_windows_event_loop()
    parser = argparse.ArgumentParser(description="Provider health check (live calls).")
    parser.add_argument("--live", action="store_true", help="required; consumes quota")
    parser.add_argument(
        "--provider", action="append", default=[], help="provider name (repeatable)"
    )
    args = parser.parse_args()
    return asyncio.run(run(args.provider, args.live))


if __name__ == "__main__":
    raise SystemExit(main())
