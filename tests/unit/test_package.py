"""Unit tests for the package scaffold."""

from __future__ import annotations

import pytest

import research_agent
from research_agent.__main__ import build_parser, main


def test_version_is_semver() -> None:
    parts = research_agent.__version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)


def test_main_prints_scaffold_notice(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    captured = capsys.readouterr()
    assert "Phase 1" in captured.out
    assert research_agent.__version__ in captured.out


def test_version_flag_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--version"])
    assert exc_info.value.code == 0
    assert research_agent.__version__ in capsys.readouterr().out
