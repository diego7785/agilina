from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RoomAdmission:
    """What a participant needs to enter the room of today's daily."""

    room_name: str
    token: str
    """The room server's access token: never logged."""
    expires_at: datetime
    """When the token stops letting its bearer in, in UTC."""
    livekit_url: str
    """The room server the web connects to."""
