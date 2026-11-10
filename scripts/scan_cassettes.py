"""Reject secrets/PII in recorded cassettes before they are committed.

This is intentionally conservative: it scans JSON/text cassette files for
common key shapes and email addresses. It is not a replacement for review.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PATTERNS = {
    "openai_key": re.compile(r"sk-[A-Za-z0-9]{20,}"),
    "groq_key": re.compile(r"gsk_[A-Za-z0-9]{20,}"),
    "google_key": re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    "generic_bearer": re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}"),
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
}


def scan(paths: list[Path]) -> int:
    problems = 0
    for path in paths:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"{path}: cannot read: {exc}", file=sys.stderr)
            problems += 1
            continue
        for name, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                problems += 1
                print(f"{path}: {name} match near offset {match.start()}", file=sys.stderr)
    return 1 if problems else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan cassettes for secrets/PII.")
    parser.add_argument("paths", nargs="*", default=["evals/cassettes"])
    args = parser.parse_args()
    roots = [Path(item) for item in args.paths]
    files = [path for root in roots for path in ([root] if root.is_file() else root.rglob("*"))]
    return scan(files)


if __name__ == "__main__":
    raise SystemExit(main())
