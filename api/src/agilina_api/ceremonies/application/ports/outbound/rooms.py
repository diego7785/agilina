"""Port to the room server (LiveKit): where the participants of a ceremony talk."""

from datetime import datetime
from typing import Protocol


class Rooms(Protocol):
    """Opens the room of a ceremony and signs who may enter it. Neither the token nor the
    credentials that sign it are ever logged. Any failure of the room server, or missing
    credentials, is ``RoomServiceUnavailableError``."""

    async def open(self, room_name: str) -> None:
        """Make sure the room exists on the server; opening one that already exists does
        nothing."""
        ...

    def admission_for(self, *, room_name: str, identity: str, expires_at: datetime) -> str:
        """The token that lets ``identity`` join only ``room_name`` until ``expires_at``,
        publishing its microphone and listening to the others."""
        ...
