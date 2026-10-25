"""GetCurrentDailyParticipants: a participant of the daily sees who else is called to it, with
their names and emails, in turn order (AGI-61)."""

import pytest

from agilina_api.ceremonies.application.dtos import DailyParticipant, ParticipantContact
from agilina_api.ceremonies.application.errors import (
    NoActiveSprintError,
    NotADailyParticipantError,
)
from agilina_api.ceremonies.application.queries.get_current_daily_participants import (
    GetCurrentDailyParticipants,
    GetCurrentDailyParticipantsHandler,
)
from agilina_shared.enums import TeamRole
from tests.api.builders import RosterBuilder, next_id
from tests.api.doubles import FakeCeremonyRoster, FakeParticipantContacts

ANA = ParticipantContact(full_name="Ana Gil", email="ana@acme.test")
CARLA = ParticipantContact(full_name="Carla Ruiz", email="carla@acme.test")


class Scenario:
    """Atlas has an active sprint with Carla first in the round and Ana second; Bruno is the
    admin of the team, not in the round."""

    def __init__(self, *, active_sprint: bool = True) -> None:
        self.atlas = next_id()
        self.ana, self.carla, self.bruno = next_id(), next_id(), next_id()
        self.roster = (
            RosterBuilder().with_participant(self.carla).with_participant(self.ana).build()
        )
        self.rosters = FakeCeremonyRoster(
            {(self.atlas, self.roster.sprint_id): self.roster} if active_sprint else {}
        )
        self.contacts = FakeParticipantContacts({self.ana: ANA, self.carla: CARLA})

    async def participants(self, user_id) -> tuple[DailyParticipant, ...]:
        handler = GetCurrentDailyParticipantsHandler(self.rosters, self.contacts)
        return await handler.handle(
            GetCurrentDailyParticipants(team_id=self.atlas, user_id=user_id)
        )


@pytest.fixture
def scenario() -> Scenario:
    return Scenario()


async def test_a_participant_sees_everyone_called_in_turn_order_with_name_and_email(scenario):
    participants = await scenario.participants(scenario.ana)

    assert participants == (
        DailyParticipant(
            room_identity=str(scenario.carla), full_name="Carla Ruiz", email="carla@acme.test"
        ),
        DailyParticipant(
            room_identity=str(scenario.ana), full_name="Ana Gil", email="ana@acme.test"
        ),
    )
    assert scenario.contacts.asked == [[scenario.carla, scenario.ana]]


async def test_the_room_identity_is_the_user_id_the_room_token_signs(scenario):
    participants = await scenario.participants(scenario.carla)

    assert [p.room_identity for p in participants] == [str(scenario.carla), str(scenario.ana)]


async def test_a_member_who_is_not_in_the_round_sees_nobody_even_the_admin(scenario):
    with pytest.raises(NotADailyParticipantError):
        await scenario.participants(scenario.bruno)

    assert scenario.contacts.asked == []


async def test_the_admin_of_the_team_in_the_round_sees_the_list_like_anyone_else():
    scenario = Scenario()
    roster = RosterBuilder().with_participant(scenario.bruno, TeamRole.ADMIN).build()
    scenario.rosters.rosters = {(scenario.atlas, roster.sprint_id): roster}
    admin = ParticipantContact(full_name="Bruno Díaz", email="bruno@acme.test")
    scenario.contacts.contacts[scenario.bruno] = admin

    participants = await scenario.participants(scenario.bruno)

    assert participants == (
        DailyParticipant(
            room_identity=str(scenario.bruno), full_name="Bruno Díaz", email="bruno@acme.test"
        ),
    )


async def test_a_team_without_an_active_sprint_has_no_participants_to_see():
    scenario = Scenario(active_sprint=False)

    with pytest.raises(NoActiveSprintError):
        await scenario.participants(scenario.ana)

    assert scenario.contacts.asked == []


async def test_a_participant_whose_account_is_gone_is_left_out_of_the_list(scenario):
    gone = next_id()
    roster = (
        RosterBuilder()
        .with_participant(scenario.carla)
        .with_participant(gone)
        .with_participant(scenario.ana)
        .build()
    )
    scenario.rosters.rosters = {(scenario.atlas, roster.sprint_id): roster}

    participants = await scenario.participants(scenario.ana)

    assert [p.room_identity for p in participants] == [str(scenario.carla), str(scenario.ana)]
    assert scenario.contacts.asked == [[scenario.carla, gone, scenario.ana]]
