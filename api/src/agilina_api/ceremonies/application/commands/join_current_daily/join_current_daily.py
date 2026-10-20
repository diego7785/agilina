from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class JoinCurrentDaily:
    tenant: str
    """The slug of the tenant the request named: it goes into the room's name (AD-29)."""
    team_id: UUID
    user_id: UUID
    """Who asks: the user behind the access token, never one named by the client."""
