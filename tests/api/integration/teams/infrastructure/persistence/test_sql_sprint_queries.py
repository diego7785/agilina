"""The read side of the sprint against a real PostgreSQL: the team's active sprint as it is
stored, with its participants in turn order, or nothing (HU-07)."""

from datetime import UTC, date, datetime

import pytest

from agilina_api.teams.application.dtos import ActiveSprintRecord
from agilina_api.teams.infrastructure.persistence.sql_sprint_queries import SqlSprintQueries
from tests.api.builders import SprintBuilder, TeamBuilder, next_id
from tests.api.integration.support import stored_sprint, stored_team, stored_user

pytestmark = pytest.mark.integration


async def test_the_active_sprint_is_read_with_its_participants_in_turn_order(session_factory):
    ana, bruno = await stored_user(session_factory), await stored_user(session_factory)
    team = await stored_team(
        session_factory, TeamBuilder().with_admin(ana.id).with_member(bruno.id)
    )
    sprint = await stored_sprint(
        session_factory,
        SprintBuilder()
        .for_team(team)
        .numbered(12)
        .with_daily_time(datetime(2026, 10, 4, 23, 0, tzinfo=UTC), "Asia/Tokyo")
        .with_participants(bruno.id, ana.id),
    )

    record = await SqlSprintQueries(session_factory).active_sprint_of(team.id)

    assert record == ActiveSprintRecord(
        sprint_id=sprint.id,
        number=12,
        start_date=date(2026, 10, 5),
        end_date=date(2026, 10, 16),
        daily_time=datetime(2026, 10, 4, 23, 0, tzinfo=UTC),
        time_zone="Asia/Tokyo",
        participants=(bruno.id, ana.id),
    )


async def test_a_sprint_without_participants_is_read_with_none(session_factory):
    team = await stored_team(session_factory)
    await stored_sprint(session_factory, SprintBuilder().for_team(team))

    record = await SqlSprintQueries(session_factory).active_sprint_of(team.id)

    assert record is not None and record.participants == ()


async def test_only_the_active_sprint_of_the_team_is_read(session_factory):
    team, other = await stored_team(session_factory), await stored_team(session_factory)
    await stored_sprint(session_factory, SprintBuilder().for_team(team).closed())
    await stored_sprint(session_factory, SprintBuilder().for_team(team).numbered(2).planned())
    active = await stored_sprint(session_factory, SprintBuilder().for_team(team).numbered(3))
    await stored_sprint(session_factory, SprintBuilder().for_team(other))

    record = await SqlSprintQueries(session_factory).active_sprint_of(team.id)

    assert record is not None and record.sprint_id == active.id


async def test_a_team_without_an_active_sprint_or_that_does_not_exist_reads_none(
    session_factory,
):
    team = await stored_team(session_factory)
    await stored_sprint(session_factory, SprintBuilder().for_team(team).closed())
    queries = SqlSprintQueries(session_factory)

    assert await queries.active_sprint_of(team.id) is None
    assert await queries.active_sprint_of(next_id()) is None
