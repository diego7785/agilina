"""TeamsBackedCeremonyRoster: the roster of the team's active sprint, with its daily's
wall-clock time (AGI-59), and what it does when the two reads of teams disagree, which the
database only allows between them (a member removed, a team deleted): it never holds a gap."""

from datetime import UTC, date, datetime, time

from agilina_api.bootstrap.context_adapters import TeamsBackedCeremonyRoster
from agilina_api.teams.application.dtos import MemberRecord, TeamView
from agilina_shared.enums import Language, OperationMode, TeamRole
from tests.api.builders import DAILY_LOCAL_TIME, NOW, SprintBuilder, next_id
from tests.api.doubles import FakeSprintQueries, FakeTeamQueries


async def _scenario(*, team_exists: bool = True, builder: SprintBuilder | None = None):
    team_id, ana, carla = next_id(), next_id(), next_id()
    sprints = FakeSprintQueries()
    sprint = await (
        (builder or SprintBuilder())
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


async def test_the_active_roster_is_the_sprint_and_its_daily_wall_clock_time():
    roster, team_id, sprint_id, _ = await _scenario()

    record = await roster.active_roster_of(team_id=team_id)

    assert record is not None
    assert (record.sprint_id, record.daily_time) == (sprint_id, DAILY_LOCAL_TIME)


async def test_the_daily_time_is_the_wall_clock_time_where_it_was_captured_even_in_summer_time():
    """09:00 in New York in daylight saving time is 13:00 UTC: the roster says 09:00."""
    summer = (
        SprintBuilder()
        .with_period(date(2027, 3, 15), date(2027, 3, 26))
        .with_daily_time(datetime(2027, 3, 15, 13, 0, tzinfo=UTC), "America/New_York")
    )
    roster, team_id, _, _ = await _scenario(builder=summer)

    record = await roster.active_roster_of(team_id=team_id)

    assert record is not None
    assert (record.daily_time, record.time_zone) == (time(9, 0), "America/New_York")


async def test_a_team_with_no_active_sprint_has_no_roster():
    roster, team_id, sprint_id, _ = await _scenario(builder=SprintBuilder().closed())

    assert await roster.active_roster_of(team_id=team_id) is None
    assert await roster.roster_of(team_id=team_id, sprint_id=sprint_id) is None


async def test_the_roster_of_a_sprint_that_is_not_the_active_one_is_none():
    roster, team_id, sprint_id, _ = await _scenario()

    assert await roster.roster_of(team_id=team_id, sprint_id=next_id()) is None
    assert await roster.roster_of(team_id=team_id, sprint_id=sprint_id) is not None
