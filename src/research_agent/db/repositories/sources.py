"""Source/document/chunk repositories."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from research_agent.db.models import Chunk as ChunkRow
from research_agent.db.models import Document as DocumentRow
from research_agent.db.models import Source as SourceRow
from research_agent.db.repositories.base import Repository
from research_agent.models.common import SourceKind, SourceStatus
from research_agent.models.sources import (
    Chunk,
    Document,
    DocumentMetadata,
    Source,
    SourceProvenance,
)


class SourceRepository(Repository):
    async def add_source(self, source: Source) -> Source:
        row = SourceRow(
            id=source.id,
            run_id=source.run_id,
            url=source.url,
            canonical_url=source.canonical_url,
            domain=source.domain,
            title=source.title,
            kind=source.kind.value,
            status=source.status.value,
            fetched_at=source.fetched_at,
            content_hash=source.content_hash,
            http_status=source.http_status,
            provenance=source.provenance.model_dump(mode="json"),
        )
        self.session.add(row)
        await self.session.flush()
        return source

    async def get_source(self, source_id: UUID) -> Source | None:
        row = await self.session.get(SourceRow, source_id)
        return source_from_row(row) if row is not None else None

    async def get_by_canonical_url(self, run_id: UUID, canonical_url: str) -> Source | None:
        stmt = select(SourceRow).where(
            SourceRow.run_id == run_id,
            SourceRow.canonical_url == canonical_url,
        )
        row = await self.session.scalar(stmt)
        return source_from_row(row) if row is not None else None

    async def list_sources(self, run_id: UUID) -> list[Source]:
        stmt = select(SourceRow).where(SourceRow.run_id == run_id).order_by(SourceRow.created_at)
        return [source_from_row(row) for row in (await self.session.scalars(stmt)).all()]

    async def add_document(self, document: Document) -> Document:
        row = DocumentRow(
            id=document.id,
            source_id=document.source_id,
            text=document.text,
            doc_metadata=document.metadata.model_dump(mode="json"),
            content_hash=document.content_hash,
        )
        self.session.add(row)
        await self.session.flush()
        return document

    async def add_chunks(self, chunks: list[Chunk]) -> list[Chunk]:
        rows = []
        for chunk in chunks:
            if chunk.embedding is None:
                raise ValueError(f"chunk {chunk.id} has no embedding")
            rows.append(
                ChunkRow(
                    id=chunk.id,
                    source_id=chunk.source_id,
                    document_id=chunk.document_id,
                    ordinal=chunk.ordinal,
                    text=chunk.text,
                    start_char=chunk.start_char,
                    end_char=chunk.end_char,
                    token_count=chunk.token_count,
                    embedding=chunk.embedding,
                )
            )
        self.session.add_all(rows)
        await self.session.flush()
        return chunks

    async def get_chunk(self, chunk_id: UUID) -> Chunk | None:
        row = await self.session.get(ChunkRow, chunk_id)
        return chunk_from_row(row) if row is not None else None

    async def list_chunks(self, source_id: UUID) -> list[Chunk]:
        stmt = select(ChunkRow).where(ChunkRow.source_id == source_id).order_by(ChunkRow.ordinal)
        return [chunk_from_row(row) for row in (await self.session.scalars(stmt)).all()]


def source_from_row(row: SourceRow) -> Source:
    return Source(
        id=row.id,
        run_id=row.run_id,
        url=row.url,
        canonical_url=row.canonical_url,
        domain=row.domain,
        title=row.title,
        kind=SourceKind(row.kind),
        status=SourceStatus(row.status),
        fetched_at=row.fetched_at,
        content_hash=row.content_hash,
        http_status=row.http_status,
        provenance=SourceProvenance.model_validate(row.provenance),
    )


def chunk_from_row(row: ChunkRow) -> Chunk:
    return Chunk(
        id=row.id,
        source_id=row.source_id,
        document_id=row.document_id,
        ordinal=row.ordinal,
        text=row.text,
        start_char=row.start_char,
        end_char=row.end_char,
        token_count=row.token_count,
        embedding=list(row.embedding) if row.embedding is not None else None,
    )


def document_from_row(row: DocumentRow) -> Document:
    return Document(
        id=row.id,
        source_id=row.source_id,
        text=row.text,
        metadata=DocumentMetadata.model_validate(row.doc_metadata),
        content_hash=row.content_hash,
    )
