"""Token-aware chunking with exact character offsets.

Offsets matter: citations point to a span in the original document, so chunks
must never reflow text. The splitter works on paragraph/sentence/word boundaries
and preserves the original substring.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import Field, model_validator

from research_agent.core.tokens import count_tokens, truncate_tail_to_tokens
from research_agent.models.common import FrozenModel
from research_agent.models.sources import ChunkDraft

PARAGRAPH_RE = re.compile(r"[^\n]+(?:\n(?!\s*\n)[^\n]+)*")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
WORD_RE = re.compile(r"\S+")


class ChunkingConfig(FrozenModel):
    target_tokens: int = Field(default=450, gt=0, le=4000)
    max_tokens: int = Field(default=600, gt=0, le=8000)
    overlap_tokens: int = Field(default=80, ge=0, le=2000)
    min_chars: int = Field(default=200, ge=0, le=10_000)

    @model_validator(mode="after")
    def _target_fits_max(self) -> ChunkingConfig:
        if self.target_tokens > self.max_tokens:
            raise ValueError("target_tokens must be <= max_tokens")
        if self.overlap_tokens >= self.target_tokens:
            raise ValueError("overlap_tokens must be < target_tokens")
        return self


@dataclass(frozen=True, slots=True)
class _Unit:
    text: str
    start: int
    end: int
    tokens: int


def _trimmed_unit(text: str, start: int, end: int) -> _Unit | None:
    segment = text[start:end]
    stripped = segment.strip()
    if not stripped:
        return None
    leading = len(segment) - len(segment.lstrip())
    trailing = len(segment) - len(segment.rstrip())
    real_start = start + leading
    real_end = end - trailing
    return _Unit(
        text=text[real_start:real_end],
        start=real_start,
        end=real_end,
        tokens=count_tokens(stripped),
    )


def _split_long_unit(text: str, unit: _Unit, max_tokens: int) -> list[_Unit]:
    """Split a single oversized unit on sentence, then word, boundaries."""
    sentences: list[_Unit] = []
    cursor = unit.start
    for match in SENTENCE_RE.finditer(text, unit.start, unit.end):
        piece = _trimmed_unit(text, cursor, match.start())
        if piece is not None:
            sentences.append(piece)
        cursor = match.end()
    tail = _trimmed_unit(text, cursor, unit.end)
    if tail is not None:
        sentences.append(tail)
    if not sentences:
        sentences = [unit]

    out: list[_Unit] = []
    for sentence in sentences:
        if sentence.tokens <= max_tokens:
            out.append(sentence)
            continue
        words = list(WORD_RE.finditer(text, sentence.start, sentence.end))
        bucket: list[_Unit] = []
        bucket_tokens = 0
        for match in words:
            piece = _trimmed_unit(text, match.start(), match.end())
            if piece is None:
                continue
            if bucket and bucket_tokens + piece.tokens > max_tokens:
                out.append(_join_units(text, bucket))
                bucket = []
                bucket_tokens = 0
            bucket.append(piece)
            bucket_tokens += piece.tokens
        if bucket:
            out.append(_join_units(text, bucket))
    return out


def _join_units(text: str, units: list[_Unit]) -> _Unit:
    start = units[0].start
    end = units[-1].end
    segment = text[start:end]
    return _Unit(
        text=segment,
        start=start,
        end=end,
        tokens=sum(unit.tokens for unit in units),
    )


def _units_for(text: str, config: ChunkingConfig) -> list[_Unit]:
    units: list[_Unit] = []
    for match in PARAGRAPH_RE.finditer(text):
        unit = _trimmed_unit(text, match.start(), match.end())
        if unit is None:
            continue
        if unit.tokens <= config.max_tokens:
            units.append(unit)
        else:
            units.extend(_split_long_unit(text, unit, config.max_tokens))
    return units


def chunk_text(text: str, config: ChunkingConfig | None = None) -> list[ChunkDraft]:
    """Split text into chunk drafts with exact offsets and bounded overlap."""
    config = config or ChunkingConfig()
    if not text.strip():
        return []
    units = _units_for(text, config)
    if not units:
        return []

    drafts: list[ChunkDraft] = []
    current: list[_Unit] = []
    current_tokens = 0

    def emit() -> None:
        nonlocal current, current_tokens
        if not current:
            return
        joined = _join_units(text, current)
        if len(joined.text) < config.min_chars and drafts:
            return
        drafts.append(
            ChunkDraft(
                text=joined.text,
                start_char=joined.start,
                end_char=joined.end,
                token_count=joined.tokens,
            )
        )

    for unit in units:
        if current and current_tokens + unit.tokens > config.target_tokens:
            previous = _join_units(text, current)
            emit()
            # Seed the next chunk with the trailing token window. This is more
            # reliable than unit-level overlap, whose units can be larger than
            # the overlap budget.
            overlap: list[_Unit] = []
            overlap_tokens = 0
            if config.overlap_tokens > 0 and previous.tokens > config.overlap_tokens:
                tail = truncate_tail_to_tokens(previous.text, config.overlap_tokens)
                relative = previous.text.rfind(tail)
                start = previous.start + (relative if relative >= 0 else 0)
                if start < previous.end:
                    segment = text[start : previous.end]
                    overlap_unit = _Unit(
                        text=segment,
                        start=start,
                        end=previous.end,
                        tokens=count_tokens(segment),
                    )
                    if overlap_unit.tokens < config.target_tokens:
                        overlap = [overlap_unit]
                        overlap_tokens = overlap_unit.tokens
            current = overlap
            current_tokens = overlap_tokens
        current.append(unit)
        current_tokens += unit.tokens
        if current_tokens >= config.max_tokens:
            emit()
            current = []
            current_tokens = 0

    emit()
    return drafts
