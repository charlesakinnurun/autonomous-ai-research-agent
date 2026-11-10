"""Postgres repository integration tests (non-vector and vector)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from research_agent.db.repositories.evidence import EvidenceRepository
from research_agent.db.repositories.runs import RunRepository
from research_agent.db.repositories.sources import SourceRepository
from research_agent.models.common import Architecture, PromptMode, RunStatus
from research_agent.models.sources import ChunkDraft, Document, Source, SourceProvenance
from research_agent.models.tools import RetrieveRequest
from research_agent.tools.embedding import HashEmbedder
from research_agent.tools.retrieval import RetrievalService


async def _run(session: object) -> object:
    repo = RunRepository(session)  # type: ignore[arg-type]
    return await repo.create(
        question="What is the example?",
        architecture=Architecture.MULTI_AGENT,
        prompt_mode=PromptMode.HANDWRITTEN,
        trace_id="trace-test",
        as_of=datetime.now(UTC),
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_run_repository_create_update_and_events(db_session: object) -> None:
    repo = RunRepository(db_session)  # type: ignore[arg-type]
    run = await repo.create(
        question="What is the example?",
        architecture=Architecture.SINGLE_AGENT,
        prompt_mode=PromptMode.HANDWRITTEN,
        trace_id="trace-1",
        as_of=datetime.now(UTC),
    )
    loaded = await repo.get(run.id)
    assert loaded is not None
    assert loaded.status is RunStatus.QUEUED
    await repo.update_status(run.id, RunStatus.RUNNING)
    loaded = await repo.get(run.id)
    assert loaded is not None and loaded.status is RunStatus.RUNNING
    event_id = await repo.add_event(
        run_id=run.id, node="intake", event_type="run_started", payload={"ok": True}
    )
    events = await repo.list_events(run.id)
    assert events[0].id == event_id
    assert events[0].payload == {"ok": True}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_source_and_document_round_trip(db_session: object) -> None:
    run = await _run(db_session)
    repo = SourceRepository(db_session)  # type: ignore[arg-type]
    source = Source(
        run_id=run.id,  # type: ignore[attr-defined]
        url="https://example.com/article",
        canonical_url="https://example.com/article",
        domain="example.com",
        provenance=SourceProvenance(provider="searxng", query="example"),
    )
    await repo.add_source(source)
    loaded = await repo.get_source(source.id)
    assert loaded is not None and loaded.domain == "example.com"
    assert await repo.get_by_canonical_url(source.run_id, source.canonical_url) is not None
    sources = await repo.list_sources(source.run_id)
    assert len(sources) == 1

    document = Document(
        source_id=source.id,
        text="Example body text.",
        content_hash="sha256:" + "b" * 64,
    )
    await repo.add_document(document)
    assert await repo.get_source(source.id) is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_vector_index_and_retrieval(db_session: object, vector_available: bool) -> None:
    run = await _run(db_session)
    source_repo = SourceRepository(db_session)  # type: ignore[arg-type]
    source = Source(
        run_id=run.id,  # type: ignore[attr-defined]
        url="https://example.com/article",
        canonical_url="https://example.com/article",
        domain="example.com",
        provenance=SourceProvenance(provider="test"),
    )
    await source_repo.add_source(source)
    document = Document(
        source_id=source.id,
        text="Alpha beta gamma delta. " * 10,
        content_hash="sha256:" + "c" * 64,
    )
    await source_repo.add_document(document)
    service = RetrievalService(HashEmbedder(dimension=384))
    chunks = await service.index_document(
        source=source,
        document=document,
        chunks=[
            ChunkDraft(
                text="Alpha beta gamma delta.",
                start_char=0,
                end_char=22,
                token_count=4,
            )
        ],
        repository=source_repo,
    )
    assert len(chunks) == 1
    evidence = EvidenceRepository(db_session)  # type: ignore[arg-type]
    response = await service.retrieve(
        RetrieveRequest(run_id=run.id, query="gamma", top_k=5),  # type: ignore[attr-defined]
        repository=evidence,
    )
    assert response.results
    assert "gamma" in response.results[0].chunk.text
    keyword = await evidence.search_keyword(run_id=run.id, query="gamma", limit=5)  # type: ignore[attr-defined]
    assert keyword
