"""Chunking tests: offsets, overlap, and bounds."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from research_agent.core.tokens import count_tokens
from research_agent.tools.chunking import ChunkingConfig, chunk_text


def _text() -> str:
    paragraphs = [
        "Alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu.",
        "Nu xi omicron pi rho sigma tau upsilon phi chi psi omega.",
        "The second paragraph continues with more evidence and context.",
        "A third paragraph adds a different perspective and a caveat.",
    ]
    return "\n\n".join(paragraphs * 3)


def test_chunks_preserve_offsets_and_bounds() -> None:
    text = _text()
    config = ChunkingConfig(target_tokens=40, max_tokens=60, overlap_tokens=8, min_chars=0)
    chunks = chunk_text(text, config)
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.text == text[chunk.start_char : chunk.end_char]
        assert chunk.token_count <= config.max_tokens
        assert count_tokens(chunk.text) <= config.max_tokens


def test_overlap_repeats_boundary_context() -> None:
    text = _text()
    config = ChunkingConfig(target_tokens=30, max_tokens=40, overlap_tokens=10, min_chars=0)
    chunks = chunk_text(text, config)
    assert len(chunks) > 1
    # At least one adjacent pair should overlap in the original text.
    assert any(
        chunks[index + 1].start_char < chunks[index].end_char for index in range(len(chunks) - 1)
    )


def test_empty_text_returns_no_chunks() -> None:
    assert chunk_text("   \n\n  ") == []


def test_long_single_paragraph_is_split() -> None:
    text = " ".join(f"word{index}" for index in range(400))
    config = ChunkingConfig(target_tokens=40, max_tokens=50, overlap_tokens=5, min_chars=0)
    chunks = chunk_text(text, config)
    assert len(chunks) > 1
    assert all(count_tokens(chunk.text) <= 50 for chunk in chunks)


def test_min_chars_drops_short_tail() -> None:
    text = "A" * 300 + "\n\nTiny."
    config = ChunkingConfig(target_tokens=50, max_tokens=60, overlap_tokens=0, min_chars=50)
    chunks = chunk_text(text, config)
    assert all(len(chunk.text) >= 50 for chunk in chunks)


def test_invalid_config_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ChunkingConfig(target_tokens=100, max_tokens=50)
    with pytest.raises(ValidationError):
        ChunkingConfig(target_tokens=100, max_tokens=200, overlap_tokens=100)
