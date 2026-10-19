"""JoinCurrentDaily: a participant of the daily asks to join today's room and gets a token of
two hours for it, a new room for each daily (AGI-59)."""

import logging
from datetime import timedelta

import pytest

from agilina_api.ceremonies.application.commands.join_current_daily import (
    ROOM_TOKEN_TTL,
    JoinCurrentDaily,
    JoinCurrentDailyHandler,
)
from agilina_api.ceremonies.application.errors import (
    DailyNotOpenError,
    NoActiveSprintError,
    NotADailyParticipantError,
    RoomServiceUnavailableError,
)
from agilina_shared.enums import TeamRole
from tests.api.builders import DAILY_TIME, RosterBuilder, next_id
from tests.api.doubles import (
    FakeCeremoniesUnitOfWork,
    FakeCeremonyRoster,
    FakeClock,
    FakeRooms,
    InMemoryCeremonyRepository,
)
from tests.api.doubles.ceremonies import Admission

LIVEKIT_URL = "wss://livekit.example.test"


class Scenario:
    """Atlas has an active sprint (2026-10-05 to 2026-10-16 in America/Bogota, daily at 09:00)
    with Ana and Carla in the round; Bruno is another member of the team, its admin, who is not
    in the round. The clock stands at the first daily's start."""

    def __init__(self, *, active_sprint: bool = True) -> None:
        self.atlas = next_id()
        self.ana, self.carla, self.bruno = next_id(), next_id(), next_id()
        self.roster = (
            RosterBuilder().with_participant(self.ana).with_participant(self.carla).build()
        )
        self.rosters = FakeCeremonyRoster(
            {(self.atlas, self.roster.sprint_id): self.roster} if active_sprint else {}
        )
        self.repository = InMemoryCeremonyRepository()
        self.uow = FakeCeremoniesUnitOfWork(self.repository)
        self.rooms = FakeRooms()
        self.clock = FakeClock(DAILY_TIME)
        self.handler = JoinCurrentDailyHandler(
            lambda: self.uow, self.rosters, self.rooms, self.clock, LIVEKIT_URL, new_id=next_id
        )

    async def join(self, user_id, tenant: str = "acme"):
        return await self.handler.handle(
            JoinCurrentDaily(tenant=tenant, team_id=self.atlas, user_id=user_id)
        )

    def ceremony(self):
        (ceremony,) = self.repository.ceremonies.values()
        return ceremony


@pytest.fixture
def scenario() -> Scenario:
    return Scenario()


async def test_a_participant_gets_a_token_of_two_hours_for_the_room_of_todays_daily(scenario):
    admission = await scenario.join(scenario.ana)

    ceremony = scenario.ceremony()
    room = f"acme-{ceremony.id}"
    expires_at = DAILY_TIME + timedelta(hours=2)
    assert admission.room_name == room
    assert admission.expires_at == expires_at
    assert admission.livekit_url == LIVEKIT_URL
    assert scenario.rooms.admissions == [Admission(room, str(scenario.ana), expires_at)]
    assert admission.token == f"token-{room}-{scenario.ana}-{expires_at.isoformat()}"
    assert scenario.rooms.opened == [room]
    assert ROOM_TOKEN_TTL == timedelta(hours=2)


async def test_the_ceremony_is_the_daily_of_today_in_the_active_sprint_and_it_is_committed(
    scenario,
):
    await scenario.join(scenario.ana)

    ceremony = scenario.ceremony()
    assert ceremony.team_id == scenario.atlas
    assert ceremony.sprint_id == scenario.roster.sprint_id
    assert ceremony.scheduled_at == DAILY_TIME
    assert scenario.uow.commits == 1


async def test_someone_who_is_not_in_the_round_gets_no_token_nor_a_ceremony_nor_a_room(scenario):
    """Bruno is a member of the team, its admin even: being in the round is what counts."""
    with pytest.raises(NotADailyParticipantError):
        await scenario.join(scenario.bruno)

    assert scenario.repository.ceremonies == {}
    assert scenario.uow.commits == 0
    assert scenario.rooms.opened == []
    assert scenario.rooms.admissions == []


async def test_the_admin_of_the_team_in_the_round_joins_like_anyone_else():
    scenario = Scenario()
    scenario.roster = RosterBuilder().with_participant(scenario.bruno, TeamRole.ADMIN).build()
    scenario.rosters.rosters = {(scenario.atlas, scenario.roster.sprint_id): scenario.roster}

    admission = await scenario.join(scenario.bruno)

    assert admission.room_name == f"acme-{scenario.ceremony().id}"


async def test_a_team_without_an_active_sprint_has_no_daily_to_join():
    scenario = Scenario(active_sprint=False)

    with pytest.raises(NoActiveSprintError):
        await scenario.join(scenario.ana)

    assert scenario.repository.ceremonies == {}
    assert scenario.rooms.opened == []


@pytest.mark.parametrize(
    "offset",
    [
        pytest.param(timedelta(minutes=-10), id="when-the-window-opens"),
        pytest.param(timedelta(minutes=59, seconds=59), id="just-before-the-grace-ends"),
    ],
)
async def test_the_daily_can_be_joined_from_ten_minutes_before_to_one_hour_after(scenario, offset):
    scenario.clock.current = DAILY_TIME + offset

    admission = await scenario.join(scenario.ana)

    assert scenario.ceremony().scheduled_at == DAILY_TIME
    assert admission.expires_at == DAILY_TIME + offset + ROOM_TOKEN_TTL


@pytest.mark.parametrize(
    "offset",
    [
        pytest.param(timedelta(minutes=-10, seconds=-1), id="before-the-window-opens"),
        pytest.param(timedelta(hours=1), id="once-the-grace-is-over"),
    ],
)
async def test_outside_the_window_the_daily_is_not_open(scenario, offset):
    scenario.clock.current = DAILY_TIME + offset

    with pytest.raises(DailyNotOpenError):
        await scenario.join(scenario.ana)

    assert scenario.repository.ceremonies == {}
    assert scenario.rooms.opened == []


async def test_the_participants_of_the_same_daily_join_the_same_room(scenario):
    ana = await scenario.join(scenario.ana)
    carla = await scenario.join(scenario.carla)

    assert ana.room_name == carla.room_name == f"acme-{scenario.ceremony().id}"
    assert [admission.identity for admission in scenario.rooms.admissions] == [
        str(scenario.ana),
        str(scenario.carla),
    ]


async def test_the_next_daily_gets_a_new_room_with_the_tenant_in_its_name(scenario):
    today = await scenario.join(scenario.ana)
    scenario.clock.advance(days=1)

    tomorrow = await scenario.join(scenario.ana)

    assert today.room_name != tomorrow.room_name
    assert today.room_name.startswith("acme-")
    assert tomorrow.room_name.startswith("acme-")
    scheduled = sorted(c.scheduled_at for c in scenario.repository.ceremonies.values())
    assert scheduled == [DAILY_TIME, DAILY_TIME + timedelta(days=1)]


async def test_the_room_is_named_after_the_tenant_that_asks(scenario):
    admission = await scenario.join(scenario.ana, tenant="ecomoda")

    assert admission.room_name == f"ecomoda-{scenario.ceremony().id}"


async def test_when_the_room_server_fails_the_ceremony_stays_and_a_retry_reuses_it(scenario):
    scenario.rooms.unavailable = True

    with pytest.raises(RoomServiceUnavailableError):
        await scenario.join(scenario.ana)

    stored = scenario.ceremony()
    assert scenario.uow.commits == 1
    assert scenario.rooms.admissions == []

    scenario.rooms.unavailable = False
    admission = await scenario.join(scenario.ana)

    assert scenario.ceremony().id == stored.id
    assert admission.room_name == f"acme-{stored.id}"


async def test_the_admission_is_logged_without_the_token(scenario, caplog):
    caplog.set_level(logging.DEBUG)

    admission = await scenario.join(scenario.ana)

    assert admission.room_name in caplog.text
    assert admission.token not in caplog.text
