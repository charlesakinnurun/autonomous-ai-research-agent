"""Embedding and hybrid retrieval tests."""

from __future__ import annotations

import math
from uuid import uuid4

import pytest

from research_agent.core.errors import ConfigurationError
from research_agent.models.sources import Chunk, ChunkDraft, Document, Source, SourceProvenance
from research_agent.models.tools import RetrievedChunk, RetrieveRequest
from research_agent.tools.embedding import FastEmbedEmbedder, HashEmbedder
from research_agent.tools.retrieval import RetrievalService, _reciprocal_rank_fusion


def test_hash_embedder_is_deterministic_and_normalized() -> None:
    embedder = HashEmbedder(dimension=32)
    first = embedder._embed("hello world")
    second = embedder._embed("hello world")
    assert first == second
    assert len(first) == 32
    assert math.isclose(sum(value * value for value in first), 1.0, rel_tol=1e-9)
    assert embedder._embed("!!!")[0] == 1.0


def test_fast_embed_dimension_check() -> None:
    embedder = FastEmbedEmbedder(dimension=4)
    assert embedder._to_list([0.1, 0.2, 0.3, 0.4]) == [0.1, 0.2, 0.3, 0.4]
    with pytest.raises(ConfigurationError):
        embedder._to_list([0.1, 0.2])


@pytest.mark.asyncio
async def test_hash_embedder_async() -> None:
    embedder = HashEmbedder(dimension=16)
    docs = await embedder.embed_documents(["a", "b"])
    query = await embedder.embed_query("a")
    assert len(docs) == 2
    assert len(query) == 16
    assert await embedder.embed_documents([]) == []


class FakeSourceRepository:
    def __init__(self) -> None:
        self.chunks: list[Chunk] = []

    async def add_chunks(self, chunks: list[Chunk]) -> list[Chunk]:
        self.chunks.extend(chunks)
        return chunks


class FakeEvidenceRepository:
    def __init__(self, vector: list[RetrievedChunk], keyword: list[RetrievedChunk]) -> None:
        self.vector = vector
        self.keyword = keyword

    async def search_vector(self, **_: object) -> list[RetrievedChunk]:
        return self.vector

    async def search_keyword(self, **_: object) -> list[RetrievedChunk]:
        return self.keyword


def _source() -> Source:
    return Source(
        run_id=uuid4(),
        url="https://example.com/a",
        canonical_url="https://example.com/a",
        domain="example.com",
        provenance=SourceProvenance(provider="test"),
    )


def _retrieved(text: str, source: Source, score: float = 0.5) -> RetrievedChunk:
    chunk = Chunk(
        source_id=source.id,
        document_id=uuid4(),
        ordinal=0,
        text=text,
        start_char=0,
        end_char=len(text),
        token_count=3,
        embedding=[0.1, 0.2],
    )
    return RetrievedChunk(chunk=chunk, source=source, score=score, vector_score=score)


@pytest.mark.asyncio
async def test_index_document_creates_embedded_chunks() -> None:
    service = RetrievalService(HashEmbedder(dimension=16))
    source = _source()
    document = Document(
        source_id=source.id,
        text="Alpha beta gamma.",
        content_hash="sha256:" + "a" * 64,
    )
    drafts = [ChunkDraft(text="Alpha beta", start_char=0, end_char=10, token_count=2)]
    repository = FakeSourceRepository()
    chunks = await service.index_document(
        source=source,
        document=document,
        chunks=drafts,
        repository=repository,  # type: ignore[arg-type]
    )
    assert len(chunks) == 1
    assert chunks[0].embedding is not None
    assert repository.chunks[0].source_id == source.id


@pytest.mark.asyncio
async def test_retrieve_merges_vector_and_keyword() -> None:
    source = _source()
    vector = [_retrieved("vector hit", source, 0.9)]
    keyword = [_retrieved("keyword hit", source, 0.8)]
    service = RetrievalService(HashEmbedder(dimension=16))
    response = await service.retrieve(
        RetrieveRequest(run_id=uuid4(), query="hit", top_k=5),
        repository=FakeEvidenceRepository(vector, keyword),  # type: ignore[arg-type]
    )
    assert len(response.results) == 2
    assert response.results[0].score >= response.results[1].score


def test_rrf_dedupes_and_normalizes() -> None:
    source = _source()
    first = _retrieved("same", source, 0.9)
    second = _retrieved("other", source, 0.1)
    merged = _reciprocal_rank_fusion([first], [first, second])
    assert len(merged) == 2
    assert merged[0].chunk.id == first.chunk.id
    assert merged[0].score == 1.0
    assert _reciprocal_rank_fusion([], []) == []
