from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class GetTeamDashboard:
    team_id: UUID
