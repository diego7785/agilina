"""TeamsBackedCeremonyRoster when the two reads of teams disagree, which the database only
allows between them (a member removed, a team deleted): the roster never holds a gap."""

from agilina_api.bootstrap.context_adapters import TeamsBackedCeremonyRoster
from agilina_api.teams.application.dtos import MemberRecord, TeamView
from agilina_shared.enums import Language, OperationMode, TeamRole
from tests.api.builders import NOW, SprintBuilder, next_id
from tests.api.doubles import FakeSprintQueries, FakeTeamQueries


async def _scenario(*, team_exists: bool = True):
    team_id, ana, carla = next_id(), next_id(), next_id()
    sprints = FakeSprintQueries()
    sprint = await (
        SprintBuilder()
        .for_team_id(team_id)
        .with_participants(carla, ana)
        .saved_in(sprints.repository)
    )
    views = {
        team_id: TeamView(
            team_id=team_id, name="Atlas", mode=OperationMode.SUPPORT, language=Language.EN
        )
    }
    teams = FakeTeamQueries(
        views=views if team_exists else {},
        members={team_id: (MemberRecord(user_id=ana, role=TeamRole.ADMIN, joined_at=NOW),)},
    )
    return TeamsBackedCeremonyRoster(teams, sprints), team_id, sprint.id, ana


async def test_a_participant_who_is_no_longer_a_member_is_left_out_and_the_turns_stay_1_to_n():
    roster, team_id, sprint_id, ana = await _scenario()

    record = await roster.roster_of(team_id=team_id, sprint_id=sprint_id)

    assert record is not None
    assert [(p.user_id, p.role, p.turn_order) for p in record.participants] == [
        (ana, TeamRole.ADMIN, 1)
    ]


async def test_a_team_that_is_gone_has_no_roster():
    roster, team_id, sprint_id, _ = await _scenario(team_exists=False)

    assert await roster.roster_of(team_id=team_id, sprint_id=sprint_id) is None
