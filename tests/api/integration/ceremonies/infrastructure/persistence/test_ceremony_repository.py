"""The ceremony repository against a real PostgreSQL: the result, its segments and its events
stored in one transaction, and the lock that keeps two deliveries of the same ceremony from
interleaving (AGI-64, AGI-126); one ceremony per occurrence of the daily, even when its
participants join at the same time (AGI-59)."""

import asyncio
import contextlib
import hashlib
from datetime import timedelta
from typing import Self
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from agilina_api.bootstrap.context_adapters import TeamsBackedCeremonyRoster
from agilina_api.ceremonies.application.commands.deliver_ceremony_result import (
    DeliverCeremonyResult,
    DeliverCeremonyResultHandler,
)
from agilina_api.ceremonies.domain.ceremony import Ceremony
from agilina_api.ceremonies.domain.errors import ResultAlreadyReceivedError
from agilina_api.ceremonies.infrastructure.persistence.ceremony_repository import (
    SqlAlchemyCeremonyRepository,
)
from agilina_api.ceremonies.infrastructure.persistence.orm_models import (
    CeremonyEventRow,
    CeremonyResultRow,
    CeremonyRow,
    TranscriptSegmentRow,
)
from agilina_api.ceremonies.infrastructure.persistence.unit_of_work import (
    SqlAlchemyCeremoniesUnitOfWork,
)
from agilina_api.shared.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from agilina_api.teams.infrastructure.persistence.sql_sprint_queries import SqlSprintQueries
from agilina_api.teams.infrastructure.persistence.team_queries import SqlTeamQueries
from agilina_shared import CeremonyEventType, CeremonyResult, CeremonyStatus
from tests.api.builders import DAILY_TIME, NOW, CeremonyBuilder, SprintBuilder, TeamBuilder, next_id
from tests.api.doubles import FakeClock
from tests.api.integration.support import stored_ceremony, stored_sprint, stored_team, stored_user
from tests.shared.builders import (
    CLOSED_AT,
    CeremonyEventBuilder,
    CeremonyResultBuilder,
    TranscriptSegmentBuilder,
)

pytestmark = pytest.mark.integration


def _digest(result: CeremonyResult) -> str:
    return hashlib.sha256(result.model_dump_json().encode()).hexdigest()


class Daily:
    """Atlas's daily, stored, with Ana and Bruno in its active sprint."""

    def __init__(self, ceremony: CeremonyBuilder, ana: UUID, bruno: UUID) -> None:
        self.ceremony, self.ana, self.bruno = ceremony, ana, bruno

    @classmethod
    async def stored(cls, session_factory) -> Self:
        ana, bruno = await stored_user(session_factory), await stored_user(session_factory)
        team = await stored_team(
            session_factory, TeamBuilder().with_admin(ana.id).with_member(bruno.id)
        )
        sprint = await stored_sprint(session_factory, SprintBuilder().for_team(team))
        ceremony = CeremonyBuilder().for_sprint(sprint)
        await stored_ceremony(session_factory, ceremony)
        return cls(ceremony, ana.id, bruno.id)

    def result(self) -> CeremonyResultBuilder:
        """Ana and then Bruno spoke in their turns; Bruno's ends the ceremony."""
        return (
            CeremonyResultBuilder()
            .for_ceremony(self.ceremony.ceremony_id)
            .with_present(self.ana)
            .with_absent(self.bruno)
            .with_segments(
                TranscriptSegmentBuilder().said_by(self.ana).saying("I closed AGI-64").build(),
                TranscriptSegmentBuilder()
                .said_by(self.bruno)
                .saying("Today I review it")
                .spanning(2400, 6100)
                .build(),
            )
            .with_events(
                CeremonyEventBuilder().build(),
                CeremonyEventBuilder()
                .of_type(CeremonyEventType.TURN_STARTED)
                .about(self.ana)
                .build(),
                CeremonyEventBuilder()
                .of_type(CeremonyEventType.CEREMONY_CLOSED)
                .happened_at(CLOSED_AT)
                .build(),
            )
        )


def _handler(session_factory, uow_factory=None) -> DeliverCeremonyResultHandler:
    roster = TeamsBackedCeremonyRoster(
        SqlTeamQueries(session_factory), SqlSprintQueries(session_factory)
    )
    factory = uow_factory or (lambda: SqlAlchemyCeremoniesUnitOfWork(session_factory))
    return DeliverCeremonyResultHandler(factory, roster, FakeClock())


async def _deliver(handler, result: CeremonyResult) -> None:
    await handler.handle(DeliverCeremonyResult(ceremony_id=result.ceremony_id, result=result))


async def _count(session_factory, row, ceremony_id: UUID) -> int:
    async with session_factory() as session:
        query = select(func.count()).select_from(row).where(row.ceremony_id == ceremony_id)
        return (await session.execute(query)).scalar_one()


async def test_the_result_its_segments_and_its_events_are_stored_in_their_order(session_factory):
    daily = await Daily.stored(session_factory)
    result = daily.result().build()

    await _deliver(_handler(session_factory), result)

    ceremony_id = daily.ceremony.ceremony_id
    async with session_factory() as session:
        stored = await session.get(CeremonyResultRow, ceremony_id)
        segments = (
            await session.scalars(
                select(TranscriptSegmentRow)
                .where(TranscriptSegmentRow.ceremony_id == ceremony_id)
                .order_by(TranscriptSegmentRow.position)
            )
        ).all()
        events = (
            await session.scalars(
                select(CeremonyEventRow)
                .where(CeremonyEventRow.ceremony_id == ceremony_id)
                .order_by(CeremonyEventRow.position)
            )
        ).all()
    assert stored is not None
    assert (stored.team_id, stored.status) == (daily.ceremony.team_id, CeremonyStatus.COMPLETED)
    assert (stored.started_at, stored.closed_at) == (result.started_at, result.closed_at)
    assert (stored.present_participants, stored.absent_participants) == ([daily.ana], [daily.bruno])
    assert (stored.degraded, stored.degradation_detail) == (False, None)
    assert (stored.payload_sha256, stored.received_at) == (_digest(result), NOW)
    assert [(s.position, s.team_id, s.user_id, s.text, s.start_ms, s.end_ms) for s in segments] == [
        (0, daily.ceremony.team_id, daily.ana, "I closed AGI-64", 0, 2400),
        (1, daily.ceremony.team_id, daily.bruno, "Today I review it", 2400, 6100),
    ]
    assert [(e.position, e.type, e.at, e.user_id) for e in events] == [
        (0, CeremonyEventType.CEREMONY_STARTED, result.events[0].at, None),
        (1, CeremonyEventType.TURN_STARTED, result.events[1].at, daily.ana),
        (2, CeremonyEventType.CEREMONY_CLOSED, CLOSED_AT, None),
    ]


async def test_a_stored_ceremony_comes_back_with_the_digest_of_its_result(session_factory):
    daily = await Daily.stored(session_factory)
    result = daily.result().build()

    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        before = await SqlAlchemyCeremonyRepository(uow.session).lock(daily.ceremony.ceremony_id)
    await _deliver(_handler(session_factory), result)
    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        after = await SqlAlchemyCeremonyRepository(uow.session).lock(daily.ceremony.ceremony_id)

    assert before is not None and before.result_digest is None
    assert (before.team_id, before.sprint_id) == (
        daily.ceremony.team_id,
        daily.ceremony.sprint_id,
    )
    assert before.scheduled_at == daily.ceremony.scheduled_at
    assert after is not None and after.result_digest == _digest(result)


async def test_a_ceremony_that_does_not_exist_is_none(session_factory):
    await Daily.stored(session_factory)

    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert await SqlAlchemyCeremonyRepository(uow.session).lock(next_id()) is None


async def test_the_same_delivery_again_stores_nothing_twice(session_factory):
    daily = await Daily.stored(session_factory)
    handler = _handler(session_factory)

    await _deliver(handler, daily.result().build())
    await _deliver(handler, daily.result().build())

    ceremony_id = daily.ceremony.ceremony_id
    assert await _count(session_factory, CeremonyResultRow, ceremony_id) == 1
    assert await _count(session_factory, TranscriptSegmentRow, ceremony_id) == 2
    assert await _count(session_factory, CeremonyEventRow, ceremony_id) == 3


async def test_a_failure_writing_the_segments_leaves_no_result_half_stored(session_factory):
    """The database refuses a segment that ends before it starts (the contract already does,
    but a worker of another version might not): the result row goes with it."""
    daily = await Daily.stored(session_factory)
    broken = (
        daily.result()
        .with_segments(
            TranscriptSegmentBuilder().said_by(daily.ana).spanning(2400, 1000).build_unchecked()
        )
        .build_unchecked()
    )

    with pytest.raises(IntegrityError, match="transcript_segment_times_ordered"):
        await _deliver(_handler(session_factory), broken)

    ceremony_id = daily.ceremony.ceremony_id
    assert await _count(session_factory, CeremonyResultRow, ceremony_id) == 0
    assert await _count(session_factory, TranscriptSegmentRow, ceremony_id) == 0
    assert await _count(session_factory, CeremonyEventRow, ceremony_id) == 0


async def test_a_result_stored_at_the_same_time_by_another_transaction_is_already_received(
    session_factory,
):
    """Only reachable without the lock (another writer): the primary key decides, and it is
    the same 409 as ``Ceremony.receive_result``'s."""
    daily = await Daily.stored(session_factory)
    first, second = (
        daily.result().build(),
        CeremonyResultBuilder().for_ceremony(daily.ceremony.ceremony_id).build(),
    )
    await _deliver(_handler(session_factory), first)
    unlocked = daily.ceremony.with_result_received(_digest(second)).aggregate()

    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        with pytest.raises(ResultAlreadyReceivedError):
            await SqlAlchemyCeremonyRepository(uow.session).add_result(
                unlocked, second, received_at=NOW
            )


async def test_any_other_integrity_error_is_not_hidden_behind_already_received(session_factory):
    """A ceremony that is not stored: its foreign key fails, and that is not a 409."""
    await Daily.stored(session_factory)
    ghost = CeremonyBuilder().with_result_received("c" * 64)
    result = CeremonyResultBuilder().for_ceremony(ghost.ceremony_id).build()

    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        with pytest.raises(IntegrityError, match="ceremony_result_ceremony_fk"):
            await SqlAlchemyCeremonyRepository(uow.session).add_result(
                ghost.aggregate(), result, received_at=NOW
            )


async def test_a_ceremony_that_received_no_result_has_nothing_to_store(session_factory):
    daily = await Daily.stored(session_factory)

    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        with pytest.raises(ValueError, match="has received no result"):
            await SqlAlchemyCeremonyRepository(uow.session).add_result(
                daily.ceremony.aggregate(), daily.result().build(), received_at=NOW
            )


# ------------------------------------------------------------------ the lock --
class _Rendezvous:
    """Holds whoever arrives until everyone has, or until ``patience`` runs out."""

    def __init__(self, parties: int, patience: float = 1.0) -> None:
        self._parties, self._patience = parties, patience
        self._arrived = 0
        self._everyone = asyncio.Event()

    async def meet(self) -> None:
        self._arrived += 1
        if self._arrived >= self._parties:
            self._everyone.set()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._everyone.wait(), self._patience)


class _LocksThenWaits:
    """The real repository, but after loading a ceremony it waits for the other delivery to
    load it too: both read before either writes, the worst interleaving. With the row lock the
    second load blocks until the first commits, so the wait runs out instead."""

    def __init__(self, inner: SqlAlchemyCeremonyRepository, rendezvous: _Rendezvous) -> None:
        self._inner, self._rendezvous = inner, rendezvous

    async def lock(self, ceremony_id: UUID) -> Ceremony | None:
        ceremony = await self._inner.lock(ceremony_id)
        await self._rendezvous.meet()
        return ceremony

    async def add_result(self, ceremony, result, *, received_at) -> None:
        await self._inner.add_result(ceremony, result, received_at=received_at)


class _RacingCeremoniesUnitOfWork(SqlAlchemyCeremoniesUnitOfWork):
    def __init__(self, session_factory, rendezvous: _Rendezvous) -> None:
        super().__init__(session_factory)
        self._rendezvous = rendezvous

    async def __aenter__(self) -> Self:
        await super().__aenter__()
        self.ceremonies = _LocksThenWaits(self.ceremonies, self._rendezvous)  # type: ignore[arg-type]
        return self


def _racing_handler(session_factory) -> DeliverCeremonyResultHandler:
    rendezvous = _Rendezvous(parties=2)
    return _handler(
        session_factory, lambda: _RacingCeremoniesUnitOfWork(session_factory, rendezvous)
    )


async def test_two_identical_deliveries_at_once_are_both_received_and_stored_once(
    session_factory,
):
    """The worker's retry can cross its first attempt. Without the lock both would see no
    result and the second insert would hit the primary key: a 409 for the same delivery."""
    daily = await Daily.stored(session_factory)
    handler = _racing_handler(session_factory)

    outcomes = await asyncio.gather(
        _deliver(handler, daily.result().build()),
        _deliver(handler, daily.result().build()),
        return_exceptions=True,
    )

    assert outcomes == [None, None]
    ceremony_id = daily.ceremony.ceremony_id
    assert await _count(session_factory, CeremonyResultRow, ceremony_id) == 1
    assert await _count(session_factory, TranscriptSegmentRow, ceremony_id) == 2
    assert await _count(session_factory, CeremonyEventRow, ceremony_id) == 3


async def test_two_different_deliveries_at_once_store_one_and_refuse_the_other(session_factory):
    daily = await Daily.stored(session_factory)
    handler = _racing_handler(session_factory)
    other = CeremonyResultBuilder().for_ceremony(daily.ceremony.ceremony_id).build()

    outcomes = await asyncio.gather(
        _deliver(handler, daily.result().build()),
        _deliver(handler, other),
        return_exceptions=True,
    )

    assert sorted(type(outcome).__name__ for outcome in outcomes) == [
        "NoneType",
        "ResultAlreadyReceivedError",
    ]
    assert await _count(session_factory, CeremonyResultRow, daily.ceremony.ceremony_id) == 1


# ------------------------------------------------------- one per occurrence --
async def _a_sprint(session_factory):
    ana = await stored_user(session_factory)
    team = await stored_team(session_factory, TeamBuilder().with_admin(ana.id))
    return await stored_sprint(session_factory, SprintBuilder().for_team(team))


def _scheduled(sprint, scheduled_at=DAILY_TIME) -> Ceremony:
    return Ceremony.schedule(
        ceremony_id=next_id(),
        team_id=sprint.team_id,
        sprint_id=sprint.id,
        scheduled_at=scheduled_at,
    )


async def _add_or_get(session_factory, ceremony: Ceremony, before=None) -> Ceremony:
    async with SqlAlchemyCeremoniesUnitOfWork(session_factory) as uow:
        if before is not None:
            await before()
        stored = await uow.ceremonies.add_or_get(ceremony)
        await uow.commit()
    return stored


async def _ceremonies_of(session_factory, sprint) -> list[UUID]:
    async with session_factory() as session:
        return list(
            await session.scalars(select(CeremonyRow.id).where(CeremonyRow.sprint_id == sprint.id))
        )


async def test_a_new_occurrence_stores_its_ceremony_as_it_came(session_factory):
    sprint = await _a_sprint(session_factory)
    ceremony = _scheduled(sprint)

    stored = await _add_or_get(session_factory, ceremony)

    assert stored.id == ceremony.id and stored.result_digest is None
    assert await _ceremonies_of(session_factory, sprint) == [ceremony.id]


async def test_the_same_occurrence_twice_is_the_same_ceremony_and_one_row(session_factory):
    sprint = await _a_sprint(session_factory)
    first = await _add_or_get(session_factory, _scheduled(sprint))

    again = await _add_or_get(session_factory, _scheduled(sprint))

    assert again.id == first.id
    assert (again.team_id, again.sprint_id) == (sprint.team_id, sprint.id)
    assert again.scheduled_at == DAILY_TIME and again.result_digest is None
    assert await _ceremonies_of(session_factory, sprint) == [first.id]


async def test_the_same_occurrence_comes_back_with_the_digest_of_its_result(session_factory):
    daily = await Daily.stored(session_factory)
    result = daily.result().build()
    await _deliver(_handler(session_factory), result)
    occurrence = Ceremony.schedule(
        ceremony_id=next_id(),
        team_id=daily.ceremony.team_id,
        sprint_id=daily.ceremony.sprint_id,
        scheduled_at=daily.ceremony.scheduled_at,
    )

    stored = await _add_or_get(session_factory, occurrence)

    assert stored.id == daily.ceremony.ceremony_id
    assert stored.result_digest == _digest(result)


async def test_participants_who_join_at_the_same_time_get_the_same_ceremony(session_factory):
    """The three reach the insert together, none committed: the unique constraint on the
    occurrence makes the later ones wait for the first and then read its ceremony."""
    sprint = await _a_sprint(session_factory)
    rendezvous = _Rendezvous(parties=3)

    stored = await asyncio.gather(
        *(
            _add_or_get(session_factory, _scheduled(sprint), before=rendezvous.meet)
            for _ in range(3)
        )
    )

    assert len({ceremony.id for ceremony in stored}) == 1
    assert await _ceremonies_of(session_factory, sprint) == [stored[0].id]


async def test_another_occurrence_of_the_same_sprint_is_another_ceremony(session_factory):
    sprint = await _a_sprint(session_factory)
    today = await _add_or_get(session_factory, _scheduled(sprint))

    tomorrow = await _add_or_get(
        session_factory, _scheduled(sprint, DAILY_TIME + timedelta(days=1))
    )

    assert tomorrow.id != today.id
    assert sorted(await _ceremonies_of(session_factory, sprint)) == sorted([today.id, tomorrow.id])


async def test_the_daily_of_another_team_at_the_same_instant_is_its_own_ceremony(session_factory):
    atlas, orion = await _a_sprint(session_factory), await _a_sprint(session_factory)
    atlas_daily = await _add_or_get(session_factory, _scheduled(atlas))

    orion_daily = await _add_or_get(session_factory, _scheduled(orion))

    assert orion_daily.id != atlas_daily.id
    assert (orion_daily.team_id, orion_daily.sprint_id) == (orion.team_id, orion.id)
    assert await _ceremonies_of(session_factory, atlas) == [atlas_daily.id]
    assert await _ceremonies_of(session_factory, orion) == [orion_daily.id]
