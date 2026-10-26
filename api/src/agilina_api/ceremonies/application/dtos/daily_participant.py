from dataclasses import dataclass


@dataclass(frozen=True)
class DailyParticipant:
    """One participant of the current daily as the room shows them, in turn order."""

    room_identity: str
    """The identity they carry in the room: ``str(user_id)``, the one their token signs."""
    full_name: str
    email: str
