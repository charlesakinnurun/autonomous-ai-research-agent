"""Token counting with a deterministic fallback.

tiktoken is an approximation for non-OpenAI models, but it is consistent across
runs, which is what budget enforcement needs. If the encoder cannot be loaded
(no network, unusual platform), fall back to a conservative character estimate.
"""

from __future__ import annotations

import functools

import tiktoken

DEFAULT_ENCODING = "cl100k_base"


@functools.lru_cache(maxsize=4)
def _encoder(encoding_name: str = DEFAULT_ENCODING) -> tiktoken.Encoding | None:
    try:
        return tiktoken.get_encoding(encoding_name)
    except Exception:
        return None


def count_tokens(text: str, *, encoding_name: str = DEFAULT_ENCODING) -> int:
    if not text:
        return 0
    encoder = _encoder(encoding_name)
    if encoder is None:
        # Conservative: ~3.5 chars/token for English, rounded up.
        return max(1, (len(text) + 3) // 4)
    return len(encoder.encode(text))


def truncate_to_tokens(text: str, max_tokens: int, *, encoding_name: str = DEFAULT_ENCODING) -> str:
    if max_tokens < 1:
        return ""
    encoder = _encoder(encoding_name)
    if encoder is None:
        return text[: max_tokens * 4]
    tokens = encoder.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return encoder.decode(tokens[:max_tokens])


def truncate_tail_to_tokens(
    text: str, max_tokens: int, *, encoding_name: str = DEFAULT_ENCODING
) -> str:
    """Return the last ``max_tokens`` tokens of ``text``."""
    if max_tokens < 1:
        return ""
    encoder = _encoder(encoding_name)
    if encoder is None:
        return text[-(max_tokens * 4) :]
    tokens = encoder.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return encoder.decode(tokens[-max_tokens:])
