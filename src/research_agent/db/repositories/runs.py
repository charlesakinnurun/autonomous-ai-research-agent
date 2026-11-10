"""Run and event repositories."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select

from research_agent.core.ids import utc_now
from research_agent.db.models import Run, RunEvent
from research_agent.db.repositories.base import Repository
from research_agent.models.common import Architecture, PromptMode, RunStatus
from research_agent.models.research import RunRecord


class RunRepository(Repository):
    async def create(
        self,
        *,
        question: str,
        architecture: Architecture,
        prompt_mode: PromptMode,
        trace_id: str,
        as_of: datetime,
        user_id: str = "local",
        config: dict[str, Any] | None = None,
        budget: dict[str, Any] | None = None,
    ) -> RunRecord:
        row = Run(
            question=question,
            architecture=architecture.value,
            prompt_mode=prompt_mode.value,
            status=RunStatus.QUEUED.value,
            as_of=as_of,
            trace_id=trace_id,
            user_id=user_id,
            config=config or {},
            budget=budget or {},
            usage={},
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.refresh(row)
        return _to_record(row)

    async def get(self, run_id: UUID) -> RunRecord | None:
        row = await self.session.get(Run, run_id)
        return _to_record(row) if row is not None else None

    async def update_status(
        self, run_id: UUID, status: RunStatus, error: str | None = None
    ) -> None:
        row = await self.session.get(Run, run_id)
        if row is None:
            return
        row.status = status.value
        if error is not None:
            row.error = {"message": error}
        row.updated_at = utc_now()

    async def add_event(
        self,
        *,
        run_id: UUID,
        node: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> int:
        event = RunEvent(
            run_id=run_id,
            node=node,
            event_type=event_type,
            payload=payload or {},
        )
        self.session.add(event)
        await self.session.flush()
        return event.id

    async def list_events(
        self, run_id: UUID, *, after_id: int = 0, limit: int = 200
    ) -> list[RunEvent]:
        stmt = (
            select(RunEvent)
            .where(RunEvent.run_id == run_id, RunEvent.id > after_id)
            .order_by(RunEvent.id)
            .limit(limit)
        )
        return list((await self.session.scalars(stmt)).all())


def _to_record(row: Run) -> RunRecord:
    return RunRecord(
        id=row.id,
        question=row.question,
        architecture=Architecture(row.architecture),
        prompt_mode=PromptMode(row.prompt_mode),
        status=RunStatus(row.status),
        trace_id=row.trace_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        error=str(row.error.get("message")) if row.error else None,
    )
