"""StartSprint: an admin configures the team's sprint, which is stored active with the daily's
time in UTC, its capture time zone and the participants in turn order; a team with an active
sprint cannot start another, and a broken rule stores nothing (HU-07)."""

import logging
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from agilina_api.teams.application.commands.start_sprint import StartSprintHandler
from agilina_api.teams.domain.errors import (
    ActiveSprintExistsError,
    DailyParticipantNotAMemberError,
    DuplicateDailyParticipantError,
    InvalidTimeZoneError,
    NoDailyParticipantsError,
    SprintEndsBeforeStartError,
    TeamNotFoundError,
)
from agilina_api.teams.domain.sprint import DailyTime, SprintPeriod, SprintStatus
from tests.api.builders import SprintBuilder, StartSprintBuilder, TeamBuilder, next_id
from tests.api.doubles import FakeActiveSprints, FakeTeamsUnitOfWork


class Scenario:
    """Atlas, administered by Ana, with Bruno and Carla as members."""

    def __init__(self) -> None:
        self.ana, self.bruno, self.carla = next_id(), next_id(), next_id()
        self.uow = FakeTeamsUnitOfWork()
        self.handler = StartSprintHandler(lambda: self.uow, new_id=next_id)

    async def a_team(self, builder: TeamBuilder | None = None):
        team = builder or (
            TeamBuilder().with_admin(self.ana).with_member(self.bruno).with_member(self.carla)
        )
        return await team.saved_in(self.uow.teams)

    def nothing_was_stored(self) -> bool:
        return self.uow.sprints.sprints == {} and self.uow.committed is False


@pytest.fixture
def scenario() -> Scenario:
    return Scenario()


async def test_starting_a_sprint_stores_it_active_and_returns_its_id(scenario):
    team = await scenario.a_team()

    sprint_id = await scenario.handler.handle(
        StartSprintBuilder()
        .for_team(team.id)
        .with_period(date(2026, 10, 5), date(2026, 10, 16))
        .with_participants(scenario.carla, scenario.ana)
        .build()
    )

    stored = scenario.uow.sprints.sprints[sprint_id]
    assert stored.team_id == team.id and stored.status is SprintStatus.ACTIVE
    assert stored.period == SprintPeriod(start=date(2026, 10, 5), end=date(2026, 10, 16))
    assert stored.participants == (scenario.carla, scenario.ana)
    assert scenario.uow.committed is True


async def test_the_first_sprint_of_a_team_is_number_1(scenario):
    team = await scenario.a_team()

    sprint_id = await scenario.handler.handle(
        StartSprintBuilder().for_team(team.id).with_participants(scenario.ana).build()
    )

    assert scenario.uow.sprints.sprints[sprint_id].number == 1


async def test_a_new_sprint_takes_the_highest_number_of_the_team_plus_one_closed_ones_included(
    scenario,
):
    team = await scenario.a_team()
    await SprintBuilder().for_team_id(team.id).numbered(1).closed().saved_in(scenario.uow.sprints)
    await SprintBuilder().for_team_id(team.id).numbered(4).closed().saved_in(scenario.uow.sprints)

    sprint_id = await scenario.handler.handle(
        StartSprintBuilder().for_team(team.id).with_participants(scenario.ana).build()
    )

    assert scenario.uow.sprints.sprints[sprint_id].number == 5


async def test_the_numbers_of_other_teams_do_not_count(scenario):
    team = await scenario.a_team()
    other_team = next_id()
    await (
        SprintBuilder().for_team_id(other_team).numbered(9).closed().saved_in(scenario.uow.sprints)
    )

    sprint_id = await scenario.handler.handle(
        StartSprintBuilder().for_team(team.id).with_participants(scenario.ana).build()
    )

    assert scenario.uow.sprints.sprints[sprint_id].number == 1


async def test_the_daily_time_is_stored_in_utc_with_the_time_zone_it_was_captured_in(scenario):
    team = await scenario.a_team()
    nine_in_bogota = datetime(2026, 10, 5, 9, 0, tzinfo=timezone(timedelta(hours=-5)))

    sprint_id = await scenario.handler.handle(
        StartSprintBuilder()
        .for_team(team.id)
        .with_daily_time(nine_in_bogota, "America/Bogota")
        .with_participants(scenario.ana)
        .build()
    )

    daily = scenario.uow.sprints.sprints[sprint_id].daily_time
    assert daily == DailyTime(
        at=datetime(2026, 10, 5, 14, 0, tzinfo=UTC), time_zone="America/Bogota"
    )
    assert daily.at.tzinfo is UTC


async def test_each_sprint_gets_a_new_id(scenario):
    first_team, second_team = await scenario.a_team(), await scenario.a_team()

    first = await scenario.handler.handle(
        StartSprintBuilder().for_team(first_team.id).with_participants(scenario.ana).build()
    )
    second = await scenario.handler.handle(
        StartSprintBuilder().for_team(second_team.id).with_participants(scenario.ana).build()
    )

    assert first != second
    assert set(scenario.uow.sprints.sprints) == {first, second}


async def test_a_team_that_does_not_exist_gets_no_sprint(scenario):
    with pytest.raises(TeamNotFoundError):
        await scenario.handler.handle(StartSprintBuilder().for_team(next_id()).build())

    assert scenario.uow.sprints.sprints == {} and scenario.uow.committed is False


async def test_a_daily_time_without_an_offset_stores_nothing(scenario):
    team = await scenario.a_team()

    with pytest.raises(ValueError, match="aware"):
        await scenario.handler.handle(
            StartSprintBuilder()
            .for_team(team.id)
            .with_daily_time(datetime(2026, 10, 5, 9, 0), "America/Bogota")
            .build()
        )

    assert scenario.uow.sprints.sprints == {} and scenario.uow.committed is False


# ---------------------------------------------------------- one active sprint --
async def test_a_team_with_an_active_sprint_cannot_start_another_and_nothing_is_stored(scenario):
    team = await scenario.a_team()
    scenario.uow.active_sprints = FakeActiveSprints({team.id})

    with pytest.raises(ActiveSprintExistsError):
        await scenario.handler.handle(
            StartSprintBuilder().for_team(team.id).with_participants(scenario.ana).build()
        )

    assert scenario.nothing_was_stored()


async def test_the_active_sprint_of_another_team_does_not_prevent_starting_one(scenario):
    team = await scenario.a_team()
    scenario.uow.active_sprints = FakeActiveSprints({next_id()})

    sprint_id = await scenario.handler.handle(
        StartSprintBuilder().for_team(team.id).with_participants(scenario.ana).build()
    )

    assert sprint_id in scenario.uow.sprints.sprints and scenario.uow.committed is True


# ----------------------------------------------------------------- the rules --
async def test_a_sprint_that_ends_before_it_starts_stores_nothing(scenario):
    team = await scenario.a_team()

    with pytest.raises(SprintEndsBeforeStartError):
        await scenario.handler.handle(
            StartSprintBuilder()
            .for_team(team.id)
            .with_period(date(2026, 10, 16), date(2026, 10, 5))
            .with_participants(scenario.ana)
            .build()
        )

    assert scenario.nothing_was_stored()


async def test_a_time_zone_that_is_not_a_known_iana_key_stores_nothing(scenario):
    team = await scenario.a_team()

    with pytest.raises(InvalidTimeZoneError):
        await scenario.handler.handle(
            StartSprintBuilder()
            .for_team(team.id)
            .with_daily_time(datetime(2026, 10, 5, 14, 0, tzinfo=UTC), "Mars/Olympus")
            .with_participants(scenario.ana)
            .build()
        )

    assert scenario.nothing_was_stored()


async def test_a_daily_without_participants_stores_nothing(scenario):
    team = await scenario.a_team()

    with pytest.raises(NoDailyParticipantsError):
        await scenario.handler.handle(StartSprintBuilder().for_team(team.id).build())

    assert scenario.nothing_was_stored()


async def test_a_participant_listed_twice_stores_nothing(scenario):
    team = await scenario.a_team()

    with pytest.raises(DuplicateDailyParticipantError):
        await scenario.handler.handle(
            StartSprintBuilder()
            .for_team(team.id)
            .with_participants(scenario.ana, scenario.bruno, scenario.ana)
            .build()
        )

    assert scenario.nothing_was_stored()


async def test_someone_outside_the_team_cannot_be_called_to_its_daily(scenario):
    team = await scenario.a_team()

    with pytest.raises(DailyParticipantNotAMemberError):
        await scenario.handler.handle(
            StartSprintBuilder()
            .for_team(team.id)
            .with_participants(scenario.ana, next_id())
            .build()
        )

    assert scenario.nothing_was_stored()


async def test_a_member_who_was_removed_cannot_be_called_to_the_daily(scenario):
    team = await scenario.a_team(
        TeamBuilder().with_admin(scenario.ana).with_removed_member(scenario.bruno)
    )

    with pytest.raises(DailyParticipantNotAMemberError):
        await scenario.handler.handle(
            StartSprintBuilder()
            .for_team(team.id)
            .with_participants(scenario.ana, scenario.bruno)
            .build()
        )

    assert scenario.nothing_was_stored()


async def test_a_member_of_another_team_only_cannot_be_called_to_this_daily(scenario):
    stranger = next_id()
    team = await scenario.a_team()
    await scenario.a_team(TeamBuilder().with_admin(stranger))

    with pytest.raises(DailyParticipantNotAMemberError):
        await scenario.handler.handle(
            StartSprintBuilder().for_team(team.id).with_participants(scenario.ana, stranger).build()
        )

    assert scenario.nothing_was_stored()


# ------------------------------------------------------------------- the log --
async def test_a_start_is_logged_with_who_asked_and_the_new_sprint(scenario, caplog):
    team = await scenario.a_team()

    with caplog.at_level(logging.INFO):
        sprint_id = await scenario.handler.handle(
            StartSprintBuilder()
            .for_team(team.id)
            .with_participants(scenario.carla)
            .requested_by_admin(scenario.ana)
            .build()
        )

    assert f"Team {team.id}: user {scenario.ana} started sprint {sprint_id}" in caplog.text
    # Only ids: the participants are not listed.
    assert str(scenario.carla) not in caplog.text


async def test_a_refused_start_logs_nothing(scenario, caplog):
    team = await scenario.a_team()
    await SprintBuilder().for_team(team).saved_in(scenario.uow.sprints)
    scenario.uow.active_sprints = FakeActiveSprints({team.id})

    with caplog.at_level(logging.INFO), pytest.raises(ActiveSprintExistsError):
        await scenario.handler.handle(
            StartSprintBuilder().for_team(team.id).with_participants(scenario.ana).build()
        )

    assert "started sprint" not in caplog.text
    assert len(scenario.uow.sprints.sprints) == 1
