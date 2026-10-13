from dataclasses import dataclass

from agilina_api.teams.application.dtos.active_sprint_view import ActiveSprintView
from agilina_api.teams.application.dtos.team_view import TeamView


@dataclass(frozen=True)
class TeamDashboardView:
    """What a member's dashboard shows: the team and, when it has one, its active sprint with
    the day N of M and the next daily computed at the current instant (HU-12)."""

    team: TeamView
    sprint: ActiveSprintView | None
