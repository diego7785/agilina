"""The one question about sprints HU-06 asks, against a real PostgreSQL: does the team have
a sprint in progress?"""

import pytest
from sqlalchemy.exc import IntegrityError

from agilina_api.shared.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from agilina_api.teams.domain.errors import ActiveSprintExistsError
from agilina_api.teams.infrastructure.persistence.sprint_queries import (
    SqlActiveSprints,
    team_has_active_sprint,
)
from tests.api.builders import SprintBuilder, next_id
from tests.api.integration.support import stored_sprint, stored_team

pytestmark = pytest.mark.integration


async def _has_active_sprint(session_factory, team_id) -> bool:
    async with session_factory() as session:
        return await team_has_active_sprint(session, team_id)


async def test_a_team_without_sprints_has_none_in_progress(session_factory):
    team = await stored_team(session_factory)

    assert await _has_active_sprint(session_factory, team.id) is False


@pytest.mark.parametrize(
    "stored_as", [SprintBuilder.planned, SprintBuilder.closed], ids=["planned", "closed"]
)
async def test_a_planned_or_closed_sprint_is_not_in_progress(session_factory, stored_as):
    team = await stored_team(session_factory)
    await stored_sprint(session_factory, stored_as(SprintBuilder().for_team(team)))

    assert await _has_active_sprint(session_factory, team.id) is False


async def test_an_active_sprint_is_in_progress(session_factory):
    team = await stored_team(session_factory)
    await stored_sprint(session_factory, SprintBuilder().for_team(team).closed())
    await stored_sprint(session_factory, SprintBuilder().for_team(team).numbered(2))

    assert await _has_active_sprint(session_factory, team.id) is True


async def test_the_active_sprint_of_another_team_does_not_count(session_factory):
    team, other = await stored_team(session_factory), await stored_team(session_factory)
    await stored_sprint(session_factory, SprintBuilder().for_team(other))

    assert await _has_active_sprint(session_factory, team.id) is False
    assert await _has_active_sprint(session_factory, next_id()) is False


async def test_the_unit_of_work_asks_it_inside_its_transaction(session_factory):
    team = await stored_team(session_factory)
    await stored_sprint(session_factory, SprintBuilder().for_team(team))

    async with SqlAlchemyUnitOfWork(session_factory) as uow:
        sprints = SqlActiveSprints(uow.session)
        assert await sprints.has_active_sprint(team.id) is True
        assert await sprints.has_active_sprint(next_id()) is False


async def test_a_team_cannot_have_two_sprints_in_progress(session_factory):
    team = await stored_team(session_factory)
    await stored_sprint(session_factory, SprintBuilder().for_team(team))

    # The repository turns the index's refusal into the domain's error (HU-07).
    with pytest.raises(ActiveSprintExistsError) as refused:
        await stored_sprint(session_factory, SprintBuilder().for_team(team).numbered(2))

    assert isinstance(refused.value.__cause__, IntegrityError)
    assert "sprint_one_active_per_team" in str(refused.value.__cause__)


async def test_two_teams_can_each_have_their_sprint_in_progress(session_factory):
    team, other = await stored_team(session_factory), await stored_team(session_factory)

    await stored_sprint(session_factory, SprintBuilder().for_team(team))
    await stored_sprint(session_factory, SprintBuilder().for_team(other))

    assert await _has_active_sprint(session_factory, other.id) is True
