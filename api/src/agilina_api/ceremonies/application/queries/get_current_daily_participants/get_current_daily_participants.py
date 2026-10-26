from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class GetCurrentDailyParticipants:
    team_id: UUID
    user_id: UUID
    """Who asks: the user behind the access token, never one named by the client."""
