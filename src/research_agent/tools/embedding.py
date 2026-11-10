"""Local embeddings.

``FastEmbedEmbedder`` is the production path (ONNX, no torch).
``HashEmbedder`` is a deterministic, dependency-free test double.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol

from research_agent.config import Settings
from research_agent.core.errors import ConfigurationError

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class Embedder(Protocol):
    dimension: int

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class HashEmbedder:
    """Stable bag-of-tokens embedding for tests and offline dry runs."""

    def __init__(self, dimension: int = 384) -> None:
        if dimension < 8:
            raise ValueError("dimension must be >= 8")
        self.dimension = dimension

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in _TOKEN_RE.findall(text.lower()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest, "big") % self.dimension
            vector[index] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            vector[0] = 1.0
            return vector
        return [value / norm for value in vector]

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class FastEmbedEmbedder:
    """Lazy ONNX embedding model. Loading happens on first use."""

    def __init__(
        self,
        *,
        model_name: str = "BAAI/bge-small-en-v1.5",
        dimension: int = 384,
        cache_dir: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.dimension = dimension
        self.cache_dir = cache_dir
        self._model: object | None = None

    def _load(self) -> object:
        if self._model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:  # pragma: no cover - dependency is declared
                raise ConfigurationError("fastembed is not installed") from exc
            self._model = TextEmbedding(model_name=self.model_name, cache_dir=self.cache_dir)
        return self._model

    def _to_list(self, vector: object) -> list[float]:
        values = [float(value) for value in vector]  # type: ignore[attr-defined]
        if len(values) != self.dimension:
            raise ConfigurationError(
                f"embedding dimension mismatch: expected {self.dimension}, got {len(values)}"
            )
        return values

    def _documents_sync(self, texts: Sequence[str]) -> list[list[float]]:
        model = self._load()
        return [self._to_list(vector) for vector in model.passage_embed(texts)]  # type: ignore[attr-defined]

    def _query_sync(self, text: str) -> list[float]:
        model = self._load()
        vectors = list(model.query_embed([text]))  # type: ignore[attr-defined]
        return self._to_list(vectors[0])

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        return await asyncio.to_thread(self._documents_sync, texts)

    async def embed_query(self, text: str) -> list[float]:
        return await asyncio.to_thread(self._query_sync, text)


def build_embedder(settings: Settings) -> FastEmbedEmbedder:
    return FastEmbedEmbedder(
        model_name=settings.embedding_model,
        dimension=settings.embedding_dim,
    )
