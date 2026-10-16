from dataclasses import dataclass
from uuid import UUID

from agilina_shared.enums import TeamRole


@dataclass(frozen=True)
class RosterParticipant:
    """One participant of the sprint's ceremonies, with their stored role and their turn."""

    user_id: UUID
    role: TeamRole
    turn_order: int
    """Position in the round, from 1."""
