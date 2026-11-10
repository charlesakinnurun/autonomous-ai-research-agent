"""Postgres implementation of the quota store.

Reservations and usage live in the same database as the run state, so a restart
does not forget the day's budget. The store assumes the caller owns the
transaction; ``Database.session`` commits or rolls back.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from research_agent.db.models import QuotaReservation as ReservationRow
from research_agent.db.models import QuotaUsage as UsageRow
from research_agent.db.repositories.base import Repository
from research_agent.models.common import QuotaReservationRecord, QuotaSnapshot


class PostgresQuotaStore(Repository):
    async def get_usage(self, provider: str, model: str, day: date) -> QuotaSnapshot:
        row = await self.session.get(UsageRow, (provider, model, day))
        if row is None:
            return QuotaSnapshot(provider=provider, model=model, day=day)
        return QuotaSnapshot(
            provider=row.provider,
            model=row.model,
            day=row.day_utc,
            requests=row.requests,
            tokens_in=row.tokens_in,
            tokens_out=row.tokens_out,
            reserved=row.reserved,
        )

    async def reserve(
        self,
        *,
        provider: str,
        model: str,
        day: date,
        tokens: int,
        expires_at: datetime,
        run_id: UUID | None,
    ) -> QuotaReservationRecord:
        statement = (
            pg_insert(UsageRow)
            .values(
                provider=provider,
                model=model,
                day_utc=day,
                requests=0,
                tokens_in=0,
                tokens_out=0,
                reserved=tokens,
            )
            .on_conflict_do_update(
                index_elements=[UsageRow.provider, UsageRow.model, UsageRow.day_utc],
                set_={"reserved": UsageRow.reserved + tokens},
            )
        )
        await self.session.execute(statement)
        reservation = ReservationRow(
            id=uuid4(),
            provider=provider,
            model=model,
            day_utc=day,
            tokens=tokens,
            expires_at=expires_at,
            run_id=run_id,
        )
        self.session.add(reservation)
        await self.session.flush()
        return QuotaReservationRecord(
            id=reservation.id,
            provider=reservation.provider,
            model=reservation.model,
            day=reservation.day_utc,
            tokens=reservation.tokens,
            expires_at=reservation.expires_at,
        )

    async def commit(
        self,
        *,
        reservation_id: UUID,
        tokens_in: int,
        tokens_out: int,
        requests: int = 1,
    ) -> None:
        reservation = await self._locked_reservation(reservation_id)
        if reservation is None:
            return
        usage = await self._locked_usage(
            reservation.provider, reservation.model, reservation.day_utc
        )
        if usage is not None:
            usage.requests += requests
            usage.tokens_in += tokens_in
            usage.tokens_out += tokens_out
            usage.reserved = max(0, usage.reserved - reservation.tokens)
        await self.session.delete(reservation)

    async def release(self, reservation_id: UUID) -> None:
        reservation = await self._locked_reservation(reservation_id)
        if reservation is None:
            return
        usage = await self.session.get(
            UsageRow,
            (reservation.provider, reservation.model, reservation.day_utc),
            with_for_update=True,
        )
        if usage is not None:
            usage.reserved = max(0, usage.reserved - reservation.tokens)
        await self.session.delete(reservation)

    async def expire_stale(self, *, now: datetime) -> int:
        stmt = select(ReservationRow).where(ReservationRow.expires_at <= now).with_for_update()
        reservations = list((await self.session.scalars(stmt)).all())
        for reservation in reservations:
            usage = await self.session.get(
                UsageRow,
                (reservation.provider, reservation.model, reservation.day_utc),
                with_for_update=True,
            )
            if usage is not None:
                usage.reserved = max(0, usage.reserved - reservation.tokens)
            await self.session.delete(reservation)
        return len(reservations)

    async def _locked_reservation(self, reservation_id: UUID) -> ReservationRow | None:
        stmt = select(ReservationRow).where(ReservationRow.id == reservation_id).with_for_update()
        return await self.session.scalar(stmt)

    async def _locked_usage(self, provider: str, model: str, day: date) -> UsageRow | None:
        stmt = (
            select(UsageRow)
            .where(
                UsageRow.provider == provider,
                UsageRow.model == model,
                UsageRow.day_utc == day,
            )
            .with_for_update()
        )
        return await self.session.scalar(stmt)
