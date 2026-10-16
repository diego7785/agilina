"""GetCeremonyContext: everything the agent worker needs before joining the room, in one call
(AGI-64, AGI-125)."""

from datetime import UTC, datetime

import pytest

from agilina_api.ceremonies.application.errors import CeremonyNotFoundError
from agilina_api.ceremonies.application.queries.get_ceremony_context import (
    GetCeremonyContext,
    GetCeremonyContextHandler,
)
from agilina_shared import CeremonyContext, ParticipantContext
from agilina_shared.enums import Language, OperationMode, TeamRole
from tests.api.builders import CeremonyBuilder, RosterBuilder, next_id
from tests.api.doubles import FakeCeremonyQueries, FakeCeremonyRoster, FakeParticipantNames


class Scenario:
    """Atlas (in Spanish, autonomous) has an active sprint from 2026-10-05 to 2026-10-16 in
    America/Bogota, with Carla first in the round and Ana, its admin, second. The daily is
    scheduled on Wednesday 2026-10-07 at 09:00 there."""

    def __init__(self) -> None:
        self.ana, self.carla = next_id(), next_id()
        self.ceremony = CeremonyBuilder().scheduled_at_instant(
            datetime(2026, 10, 7, 14, 0, tzinfo=UTC)
        )
        record = self.ceremony.build()
        self.ceremonies = FakeCeremonyQueries({self.ceremony.ceremony_id: record})
        self.rosters = FakeCeremonyRoster(
            {
                (record.team_id, record.sprint_id): RosterBuilder()
                .in_language(Language.ES)
                .in_mode(OperationMode.AUTONOMOUS)
                .with_participant(self.carla)
                .with_participant(self.ana, TeamRole.ADMIN)
                .build()
            }
        )
        self.names = FakeParticipantNames({self.ana: "Ana Gil", self.carla: "Carla Ruiz"})

    async def context(self, ceremony_id=None, tenant: str = "acme") -> CeremonyContext:
        handler = GetCeremonyContextHandler(self.ceremonies, self.rosters, self.names)
        return await handler.handle(
            GetCeremonyContext(tenant=tenant, ceremony_id=ceremony_id or self.ceremony.ceremony_id)
        )


async def test_one_call_gives_the_tenant_sprint_day_participants_order_language_and_mode():
    scenario = Scenario()
    ceremony = scenario.ceremony

    context = await scenario.context()

    assert context == CeremonyContext(
        tenant="acme",
        ceremony_id=ceremony.ceremony_id,
        team_id=ceremony.team_id,
        sprint_id=ceremony.sprint_id,
        room=f"acme-{ceremony.ceremony_id}",
        language=Language.ES,
        mode=OperationMode.AUTONOMOUS,
        sprint_day=3,
        sprint_total_days=12,
        participants=[
            ParticipantContext(
                user_id=scenario.carla,
                name="Carla Ruiz",
                room_identity=str(scenario.carla),
                role=TeamRole.MEMBER,
                turn_order=1,
            ),
            ParticipantContext(
                user_id=scenario.ana,
                name="Ana Gil",
                room_identity=str(scenario.ana),
                role=TeamRole.ADMIN,
                turn_order=2,
            ),
        ],
    )


async def test_the_thresholds_are_the_ones_the_contract_sets_by_default():
    context = await Scenario().context()

    assert (context.silence_seconds, context.stuck_turn_seconds) == (10, 30)


async def test_the_tenant_of_the_request_names_the_room_and_travels_in_the_context():
    scenario = Scenario()

    context = await scenario.context(tenant="ecomoda")

    assert context.tenant == "ecomoda"
    assert context.room == f"ecomoda-{scenario.ceremony.ceremony_id}"


async def test_the_roster_is_asked_for_the_team_and_the_sprint_of_the_ceremony():
    scenario = Scenario()
    record = scenario.ceremony.build()

    await scenario.context()

    assert scenario.rosters.asked == [(record.team_id, record.sprint_id)]


async def test_a_daily_late_in_the_evening_is_on_the_sprint_day_of_its_time_zone():
    """22:30 of Wednesday in Bogota is already Thursday in UTC: the day is still the 3rd."""
    scenario = Scenario()
    late = scenario.ceremony.scheduled_at_instant(datetime(2026, 10, 8, 3, 30, tzinfo=UTC))
    scenario.ceremonies.ceremonies[late.ceremony_id] = late.build()

    context = await scenario.context()

    assert (context.sprint_day, context.sprint_total_days) == (3, 12)


async def test_a_ceremony_that_does_not_exist_is_not_found():
    scenario = Scenario()

    with pytest.raises(CeremonyNotFoundError):
        await scenario.context(next_id())

    assert scenario.rosters.asked == []


async def test_a_ceremony_scheduled_before_its_sprint_starts_is_not_found():
    """The day before 2026-10-05 has no day N of the sprint: it is not a 500."""
    scenario = Scenario()
    early = scenario.ceremony.scheduled_at_instant(datetime(2026, 10, 4, 14, 0, tzinfo=UTC))
    scenario.ceremonies.ceremonies[early.ceremony_id] = early.build()

    with pytest.raises(CeremonyNotFoundError):
        await scenario.context()


async def test_a_ceremony_whose_sprint_is_no_longer_the_active_one_is_not_found():
    scenario = Scenario()
    scenario.rosters.rosters.clear()

    with pytest.raises(CeremonyNotFoundError):
        await scenario.context()
