"""Evidence indexing and hybrid retrieval."""

from __future__ import annotations

from uuid import UUID, uuid4

from research_agent.db.repositories.evidence import EvidenceRepository
from research_agent.db.repositories.sources import SourceRepository
from research_agent.models.sources import Chunk, ChunkDraft, Document, Source
from research_agent.models.tools import RetrievedChunk, RetrieveRequest, RetrieveResponse
from research_agent.tools.embedding import Embedder

RRF_K = 60


class RetrievalService:
    def __init__(self, embedder: Embedder) -> None:
        self.embedder = embedder

    async def index_document(
        self,
        *,
        source: Source,
        document: Document,
        chunks: list[ChunkDraft],
        repository: SourceRepository,
    ) -> list[Chunk]:
        if not chunks:
            return []
        embeddings = await self.embedder.embed_documents([chunk.text for chunk in chunks])
        rows = [
            Chunk(
                id=uuid4(),
                source_id=source.id,
                document_id=document.id,
                ordinal=ordinal,
                text=draft.text,
                start_char=draft.start_char,
                end_char=draft.end_char,
                token_count=draft.token_count,
                embedding=embedding,
            )
            for ordinal, (draft, embedding) in enumerate(zip(chunks, embeddings, strict=True))
        ]
        await repository.add_chunks(rows)
        return rows

    async def retrieve(
        self,
        request: RetrieveRequest,
        *,
        repository: EvidenceRepository,
    ) -> RetrieveResponse:
        query_vector = await self.embedder.embed_query(request.query)
        candidate_k = max(request.top_k * 3, request.top_k)
        vector_results = await repository.search_vector(
            run_id=request.run_id,
            query_embedding=query_vector,
            limit=candidate_k,
        )
        keyword_results: list[RetrievedChunk] = []
        if request.hybrid:
            keyword_results = await repository.search_keyword(
                run_id=request.run_id,
                query=request.query,
                limit=candidate_k,
            )

        merged = _reciprocal_rank_fusion(vector_results, keyword_results)
        filtered = [item for item in merged if item.score >= request.min_score]
        return RetrieveResponse(query=request.query, results=filtered[: request.top_k])


def _reciprocal_rank_fusion(
    vector_results: list[RetrievedChunk],
    keyword_results: list[RetrievedChunk],
) -> list[RetrievedChunk]:
    scores: dict[UUID, float] = {}
    by_id: dict[UUID, RetrievedChunk] = {}
    for rank, item in enumerate(vector_results):
        scores[item.chunk.id] = scores.get(item.chunk.id, 0.0) + 1.0 / (RRF_K + rank + 1)
        by_id[item.chunk.id] = item
    for rank, item in enumerate(keyword_results):
        scores[item.chunk.id] = scores.get(item.chunk.id, 0.0) + 1.0 / (RRF_K + rank + 1)
        by_id.setdefault(item.chunk.id, item)

    if not scores:
        return []
    max_score = max(scores.values())
    merged: list[RetrievedChunk] = []
    for chunk_id, raw_score in sorted(scores.items(), key=lambda pair: pair[1], reverse=True):
        item = by_id[chunk_id]
        merged.append(
            item.model_copy(
                update={
                    "score": raw_score / max_score if max_score else 0.0,
                    "vector_score": item.vector_score,
                    "keyword_score": item.keyword_score,
                }
            )
        )
    return merged
