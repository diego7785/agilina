from agilina_api.teams.application.dtos import TeamDashboardView
from agilina_api.teams.application.ports.outbound import TeamQueries
from agilina_api.teams.application.queries.get_active_sprint import (
    GetActiveSprint,
    GetActiveSprintHandler,
)
from agilina_api.teams.application.queries.get_team_dashboard.get_team_dashboard import (
    GetTeamDashboard,
)
from agilina_api.teams.domain.errors import TeamNotFoundError


class GetTeamDashboardHandler:
    """It does not check who asks: the route lets only the team's members get here.

    The team and its active sprint come in one answer so that the dashboard is drawn from a
    single read. The sprint's day N of M and its next daily are the ones ``GetActiveSprint``
    computes, so both queries always agree on the schedule (AD-31).
    """

    def __init__(self, queries: TeamQueries, active_sprint: GetActiveSprintHandler) -> None:
        self._queries = queries
        self._active_sprint = active_sprint

    async def handle(self, query: GetTeamDashboard) -> TeamDashboardView:
        team = await self._queries.get_team(query.team_id)
        if team is None:
            raise TeamNotFoundError(f"Team {query.team_id} does not exist")
        sprint = await self._active_sprint.handle(GetActiveSprint(team_id=query.team_id))
        return TeamDashboardView(team=team, sprint=sprint)
