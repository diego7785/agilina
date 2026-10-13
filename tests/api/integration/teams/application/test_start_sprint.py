"""StartSprint against a real PostgreSQL: the sprint and its participants are stored in one
transaction, the read side returns it with its day N of M and next daily, and two starts at
once leave a single active sprint (HU-07)."""

import asyncio
from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import text

from agilina_api.teams.application.queries.get_active_sprint import GetActiveSprint
from agilina_api.teams.domain.errors import ActiveSprintExistsError
from agilina_shared.sprint_calendar import SprintDay, SprintPhase
from tests.api.builders import DAILY_TIME, SprintBuilder, StartSprintBuilder, TeamBuilder
from tests.api.integration.support import stored_sprint, stored_team, stored_user
from tests.api.integration.world import World

pytestmark = pytest.mark.integration


async def test_a_started_sprint_is_read_back_with_its_day_and_next_daily(session_factory):
    world = World(session_factory)
    ana, bruno = await stored_user(session_factory), await stored_user(session_factory)
    team = await stored_team(
        session_factory, TeamBuilder().with_admin(ana.id).with_member(bruno.id)
    )

    sprint_id = await world.start_sprint.handle(
        StartSprintBuilder().for_team(team.id).with_participants(bruno.id, ana.id).build()
    )
    view = await world.active_sprint.handle(GetActiveSprint(team_id=team.id))

    assert view is not None
    assert view.sprint.sprint_id == sprint_id
    assert view.sprint.participants == (bruno.id, ana.id)
    assert view.sprint.number == 1
    assert view.day == SprintDay(number=0, total=12, phase=SprintPhase.NOT_STARTED)
    assert view.next_daily_at == DAILY_TIME


async def test_a_new_sprint_takes_the_next_number_of_its_team_after_a_closed_one(session_factory):
    world = World(session_factory)
    ana = await stored_user(session_factory)
    team = await stored_team(session_factory, TeamBuilder().with_admin(ana.id))
    other = await stored_team(session_factory, TeamBuilder().with_admin(ana.id))
    await stored_sprint(session_factory, SprintBuilder().for_team(team).numbered(1).closed())
    await stored_sprint(session_factory, SprintBuilder().for_team(team).numbered(2).closed())
    await stored_sprint(session_factory, SprintBuilder().for_team(other).numbered(9).closed())

    await world.start_sprint.handle(
        StartSprintBuilder().for_team(team.id).with_participants(ana.id).build()
    )
    view = await world.active_sprint.handle(GetActiveSprint(team_id=team.id))

    assert view is not None and view.sprint.number == 3


async def test_two_simultaneous_starts_leave_one_sprint_and_a_conflict(session_factory, engine):
    """Each start runs in its own transaction and connection. The team's lock orders them:
    the second one finds the first sprint already there and is refused with the domain's
    ``ActiveSprintExistsError``, never with an ``IntegrityError`` from the index."""
    world = World(session_factory)
    ana, bruno = await stored_user(session_factory), await stored_user(session_factory)
    team = await stored_team(
        session_factory, TeamBuilder().with_admin(ana.id).with_member(bruno.id)
    )
    start = StartSprintBuilder().for_team(team.id).requested_by_admin(ana.id)

    outcomes = await asyncio.gather(
        world.start_sprint.handle(start.with_participants(ana.id, bruno.id).build()),
        world.start_sprint.handle(
            start.with_period(date(2026, 10, 12), date(2026, 10, 23))
            .with_participants(bruno.id)
            .build()
        ),
        return_exceptions=True,
    )

    started = [outcome for outcome in outcomes if isinstance(outcome, UUID)]
    refused = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
    assert len(started) == 1
    assert len(refused) == 1 and type(refused[0]) is ActiveSprintExistsError
    assert refused[0].__cause__ is None  # refused by the check under the lock, not the index
    async with engine.connect() as connection:
        stored = (
            await connection.execute(
                text("SELECT id, status::text, number FROM sprint WHERE team_id = :id"),
                {"id": team.id},
            )
        ).all()
    assert [tuple(row) for row in stored] == [(started[0], "active", 1)]
    view = await world.active_sprint.handle(GetActiveSprint(team_id=team.id))
    assert view is not None and view.sprint.sprint_id == started[0]
