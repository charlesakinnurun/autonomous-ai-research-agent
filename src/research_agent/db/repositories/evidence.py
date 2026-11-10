"""Vector + keyword evidence retrieval."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import func, select

from research_agent.db.models import Chunk as ChunkRow
from research_agent.db.models import Source as SourceRow
from research_agent.db.repositories.base import Repository
from research_agent.db.repositories.sources import chunk_from_row, source_from_row
from research_agent.models.tools import RetrievedChunk


class EvidenceRepository(Repository):
    async def search_vector(
        self, *, run_id: UUID, query_embedding: list[float], limit: int = 20
    ) -> list[RetrievedChunk]:
        distance = ChunkRow.embedding.cosine_distance(query_embedding).label("distance")
        stmt = (
            select(ChunkRow, SourceRow, distance)
            .join(SourceRow, ChunkRow.source_id == SourceRow.id)
            .where(SourceRow.run_id == run_id)
            .order_by(distance)
            .limit(limit)
        )
        rows = cast(
            list[tuple[ChunkRow, SourceRow, float]],
            (await self.session.execute(stmt)).all(),
        )
        results: list[RetrievedChunk] = []
        for chunk_row, source_row, distance_value in rows:
            score = max(0.0, min(1.0, 1.0 - float(distance_value)))
            results.append(
                RetrievedChunk(
                    chunk=chunk_from_row(chunk_row),
                    source=source_from_row(source_row),
                    score=score,
                    vector_score=score,
                )
            )
        return results

    async def search_keyword(
        self, *, run_id: UUID, query: str, limit: int = 20
    ) -> list[RetrievedChunk]:
        tsquery = func.plainto_tsquery("english", query)
        rank = func.ts_rank_cd(ChunkRow.tsv, tsquery).label("rank")
        stmt = (
            select(ChunkRow, SourceRow, rank)
            .join(SourceRow, ChunkRow.source_id == SourceRow.id)
            .where(SourceRow.run_id == run_id, ChunkRow.tsv.op("@@")(tsquery))
            .order_by(rank.desc())
            .limit(limit)
        )
        rows = cast(
            list[tuple[ChunkRow, SourceRow, float]],
            (await self.session.execute(stmt)).all(),
        )
        results: list[RetrievedChunk] = []
        for chunk_row, source_row, rank_value in rows:
            score = max(0.0, min(1.0, float(rank_value)))
            results.append(
                RetrievedChunk(
                    chunk=chunk_from_row(chunk_row),
                    source=source_from_row(source_row),
                    score=score,
                    keyword_score=score,
                )
            )
        return results

    async def list_for_run(self, run_id: UUID, *, limit: int = 200) -> list[RetrievedChunk]:
        stmt = (
            select(ChunkRow, SourceRow)
            .join(SourceRow, ChunkRow.source_id == SourceRow.id)
            .where(SourceRow.run_id == run_id)
            .order_by(SourceRow.created_at, ChunkRow.ordinal)
            .limit(limit)
        )
        rows = cast(
            list[tuple[ChunkRow, SourceRow]],
            (await self.session.execute(stmt)).all(),
        )
        return [
            RetrievedChunk(
                chunk=chunk_from_row(chunk_row),
                source=source_from_row(source_row),
                score=0.0,
            )
            for chunk_row, source_row in rows
        ]
