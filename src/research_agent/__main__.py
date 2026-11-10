"""CLI entry point.

Phase 1 proves the package is installable and that the contracts/tool layer
import cleanly. The research CLI arrives in Phase 2.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from research_agent import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research-agent",
        description="Evidence-first autonomous research agent (Phase 1).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the scaffold CLI and return a process exit code."""
    parser = build_parser()
    parser.parse_args(argv)
    print(f"autonomous-research-agent {__version__} (Phase 1)")
    print("Contracts, schema, and tools are available; the research graph lands in Phase 2.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
