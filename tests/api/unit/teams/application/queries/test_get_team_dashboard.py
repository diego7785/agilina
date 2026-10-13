"""GetTeamDashboard: the team and its active sprint in one answer, with the day N of M and the
next daily the sprint query computes (HU-12).

The sprint of the cases runs from Monday 2026-10-05 to Friday 2026-10-16 with the daily at 09:00
in America/Bogota, that is 14:00 UTC.
"""

from datetime import UTC, datetime

import pytest

from agilina_api.teams.application.dtos import TeamView
from agilina_api.teams.application.queries.get_active_sprint import (
    GetActiveSprint,
    GetActiveSprintHandler,
)
from agilina_api.teams.application.queries.get_team_dashboard import (
    GetTeamDashboard,
    GetTeamDashboardHandler,
)
from agilina_api.teams.domain.errors import TeamNotFoundError
from agilina_shared.enums import Language, OperationMode
from agilina_shared.sprint_calendar import SprintDay, SprintPhase
from tests.api.builders import NOW, SprintBuilder, next_id
from tests.api.doubles import FakeClock, FakeSprintQueries, FakeTeamQueries


class Scenario:
    def __init__(self) -> None:
        self.team_id = next_id()
        self.team = TeamView(
            team_id=self.team_id,
            name="Atlas",
            mode=OperationMode.SUPPORT,
            language=Language.EN,
        )
        self.sprint_queries = FakeSprintQueries()
        self.clock = FakeClock()
        self.handler = GetTeamDashboardHandler(
            FakeTeamQueries(views={self.team_id: self.team}),
            GetActiveSprintHandler(self.sprint_queries, self.clock),
        )

    async def a_sprint(self, builder: SprintBuilder | None = None):
        builder = builder or SprintBuilder()
        return await builder.for_team_id(self.team_id).saved_in(self.sprint_queries.repository)

    async def at(self, instant: datetime):
        self.clock.current = instant
        return await self.handler.handle(GetTeamDashboard(team_id=self.team_id))


@pytest.fixture
def scenario() -> Scenario:
    return Scenario()


async def test_it_carries_the_team_as_it_is_stored(scenario):
    view = await scenario.at(NOW)

    assert view.team == scenario.team


async def test_a_team_without_an_active_sprint_has_no_sprint(scenario):
    await scenario.a_sprint(SprintBuilder().closed())

    assert (await scenario.at(NOW)).sprint is None


async def test_the_sprint_comes_with_the_day_and_the_next_daily_the_sprint_query_computes(
    scenario,
):
    sprint = await scenario.a_sprint()
    now = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)

    view = await scenario.at(now)

    assert view.sprint is not None
    assert view.sprint.sprint.sprint_id == sprint.id
    assert view.sprint.day == SprintDay(number=3, total=12, phase=SprintPhase.IN_PROGRESS)
    assert view.sprint.next_daily_at == datetime(2026, 10, 8, 14, 0, tzinfo=UTC)
    same_query = await GetActiveSprintHandler(scenario.sprint_queries, scenario.clock).handle(
        GetActiveSprint(team_id=scenario.team_id)
    )
    assert view.sprint == same_query


async def test_a_team_that_does_not_exist_is_not_found():
    handler = GetTeamDashboardHandler(
        FakeTeamQueries(), GetActiveSprintHandler(FakeSprintQueries(), FakeClock())
    )

    with pytest.raises(TeamNotFoundError):
        await handler.handle(GetTeamDashboard(team_id=next_id()))
