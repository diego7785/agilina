"""DeliverCeremonyResult: the agent worker hands over the attributed transcript and the events
when the ceremony closes (AGI-64, AGI-126)."""

import hashlib
from datetime import UTC, datetime

import pytest

from agilina_api.ceremonies.application.commands.deliver_ceremony_result import (
    DeliverCeremonyResult,
    DeliverCeremonyResultHandler,
)
from agilina_api.ceremonies.application.errors import (
    CeremonyNotFoundError,
    ResultOfAnotherCeremonyError,
)
from agilina_api.ceremonies.domain.errors import NotAParticipantError, ResultAlreadyReceivedError
from agilina_shared import CeremonyEventType, CeremonyResult
from tests.api.builders import CeremonyBuilder, RosterBuilder, next_id
from tests.api.doubles import (
    FakeCeremoniesUnitOfWork,
    FakeCeremonyRoster,
    FakeClock,
    InMemoryCeremonyRepository,
)
from tests.api.doubles.ceremonies import StoredResult
from tests.shared.builders import (
    CeremonyEventBuilder,
    CeremonyResultBuilder,
    TranscriptSegmentBuilder,
)


def _digest(result: CeremonyResult) -> str:
    return hashlib.sha256(result.model_dump_json().encode()).hexdigest()


class Scenario:
    """Atlas has a daily in its active sprint (2026-10-05 to 2026-10-16 in America/Bogota) with
    Ana and Carla in the round; nothing has been delivered for it yet."""

    def __init__(self, ceremony: CeremonyBuilder | None = None) -> None:
        self.ana, self.carla = next_id(), next_id()
        self.ceremony = ceremony or CeremonyBuilder()
        self.repository = InMemoryCeremonyRepository(self.ceremony.aggregate())
        self.uow = FakeCeremoniesUnitOfWork(self.repository)
        self.rosters = FakeCeremonyRoster(
            {
                (self.ceremony.team_id, self.ceremony.sprint_id): RosterBuilder()
                .with_participant(self.ana)
                .with_participant(self.carla)
                .build()
            }
        )
        self.clock = FakeClock()

    def result(self) -> CeremonyResultBuilder:
        """What the worker captured: Ana and Carla spoke in their turns."""
        return (
            CeremonyResultBuilder()
            .for_ceremony(self.ceremony.ceremony_id)
            .with_present(self.ana, self.carla)
            .with_segments(
                TranscriptSegmentBuilder().said_by(self.ana).build(),
                TranscriptSegmentBuilder().said_by(self.carla).spanning(2400, 5000).build(),
            )
            .with_events(
                CeremonyEventBuilder().build(),
                CeremonyEventBuilder()
                .of_type(CeremonyEventType.TURN_STARTED)
                .about(self.ana)
                .build(),
            )
        )

    async def deliver(self, result: CeremonyResult, ceremony_id=None) -> None:
        handler = DeliverCeremonyResultHandler(lambda: self.uow, self.rosters, self.clock)
        await handler.handle(
            DeliverCeremonyResult(
                ceremony_id=ceremony_id or self.ceremony.ceremony_id, result=result
            )
        )


async def test_a_first_delivery_is_stored_as_it_came_and_committed():
    scenario = Scenario()
    result = scenario.result().build()

    await scenario.deliver(result)

    assert scenario.repository.results == {
        scenario.ceremony.ceremony_id: StoredResult(_digest(result), result, scenario.clock.now())
    }
    assert scenario.uow.commits == 1


async def test_the_same_delivery_again_stores_nothing_and_does_not_fail():
    """The worker retries until it gets an answer (CA6): a retry is not a second result."""
    scenario = Scenario()
    result = scenario.result().build()
    await scenario.deliver(result)
    first_received_at = scenario.clock.now()
    scenario.clock.advance(minutes=5)

    await scenario.deliver(scenario.result().build())

    stored = scenario.repository.results[scenario.ceremony.ceremony_id]
    assert stored == StoredResult(_digest(result), result, first_received_at)
    assert scenario.uow.commits == 1


async def test_the_same_delivery_again_is_received_after_the_sprint_stops_being_active():
    """The first 202 may never reach the worker: its retry must not end in a 404 it keeps."""
    scenario = Scenario()
    await scenario.deliver(scenario.result().build())
    scenario.rosters.rosters.clear()

    await scenario.deliver(scenario.result().build())

    assert scenario.uow.commits == 1


async def test_another_result_for_a_ceremony_that_has_one_is_refused_and_not_stored():
    first = CeremonyResultBuilder()
    scenario = Scenario()
    stored = first.for_ceremony(scenario.ceremony.ceremony_id).build()
    await scenario.deliver(stored)

    with pytest.raises(ResultAlreadyReceivedError):
        await scenario.deliver(scenario.result().build())

    assert scenario.repository.results[scenario.ceremony.ceremony_id].result == stored
    assert scenario.uow.commits == 1


async def test_a_segment_or_an_event_of_someone_who_is_not_a_participant_is_refused():
    scenario = Scenario()
    stranger = next_id()
    result = (
        scenario.result()
        .with_segments(
            TranscriptSegmentBuilder().said_by(scenario.ana).build(),
            TranscriptSegmentBuilder().said_by(stranger).build(),
        )
        .with_events(
            CeremonyEventBuilder().build(),
            CeremonyEventBuilder().of_type(CeremonyEventType.TURN_STARTED).about(stranger).build(),
        )
        .build()
    )

    with pytest.raises(NotAParticipantError) as raised:
        await scenario.deliver(result)

    assert raised.value.fields == ("segments.1.user_id", "events.1.user_id")
    assert scenario.repository.results == {}
    assert scenario.uow.commits == 0


async def test_who_may_speak_is_the_roster_of_the_ceremony_s_team_and_sprint():
    scenario = Scenario()

    await scenario.deliver(scenario.result().build())

    assert scenario.rosters.asked == [(scenario.ceremony.team_id, scenario.ceremony.sprint_id)]


async def test_a_result_of_another_ceremony_is_refused_before_anything_is_looked_up():
    scenario = Scenario()
    result = scenario.result().for_ceremony(next_id()).build()

    with pytest.raises(ResultOfAnotherCeremonyError):
        await scenario.deliver(result)

    assert scenario.rosters.asked == []
    assert scenario.repository.results == {}


async def test_a_ceremony_that_does_not_exist_is_not_found():
    scenario = Scenario()
    unknown = next_id()

    with pytest.raises(CeremonyNotFoundError):
        await scenario.deliver(scenario.result().for_ceremony(unknown).build(), unknown)

    assert scenario.rosters.asked == []


async def test_a_ceremony_whose_sprint_is_no_longer_the_active_one_is_not_found():
    scenario = Scenario()
    scenario.rosters.rosters.clear()

    with pytest.raises(CeremonyNotFoundError):
        await scenario.deliver(scenario.result().build())

    assert scenario.repository.results == {}


async def test_a_ceremony_scheduled_before_its_sprint_starts_is_not_found():
    """The same answer the worker got when it asked for the context (AGI-125)."""
    early = CeremonyBuilder().scheduled_at_instant(datetime(2026, 10, 4, 14, 0, tzinfo=UTC))
    scenario = Scenario(early)

    with pytest.raises(CeremonyNotFoundError):
        await scenario.deliver(scenario.result().build())

    assert scenario.repository.results == {}


async def test_a_degraded_ceremony_where_nobody_spoke_is_stored():
    scenario = Scenario()
    result = (
        CeremonyResultBuilder()
        .for_ceremony(scenario.ceremony.ceremony_id)
        .degraded("The transcription service did not respond")
        .build()
    )

    await scenario.deliver(result)

    assert scenario.repository.results[scenario.ceremony.ceremony_id].result == result
