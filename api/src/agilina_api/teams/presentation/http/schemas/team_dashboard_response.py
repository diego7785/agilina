from pydantic import BaseModel, Field

from agilina_api.teams.presentation.http.schemas.dashboard_sprint_response import (
    DashboardSprintResponse,
)
from agilina_api.teams.presentation.http.schemas.dashboard_team_response import (
    DashboardTeamResponse,
)
from agilina_api.teams.presentation.http.schemas.next_ceremony_response import NextCeremonyResponse


class TeamDashboardResponse(BaseModel):
    team: DashboardTeamResponse
    sprint: DashboardSprintResponse | None = Field(
        description="The team's active sprint, or `null` when it has none."
    )
    next_ceremony: NextCeremonyResponse | None = Field(
        description=(
            "The next daily, or `null` when the team has no active sprint or its last daily "
            "has already started."
        )
    )
    can_configure: bool = Field(
        description=(
            "Whether the interface draws the Settings entry: true for an admin. It only "
            "decides what is drawn; the API still checks the permission on every settings route."
        )
    )
