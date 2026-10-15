"""Builder of ``ParticipantContext``."""

from dataclasses import dataclass, field, replace
from typing import Self
from uuid import UUID

from agilina_shared.contract import ParticipantContext
from agilina_shared.enums import TeamRole
from tests.shared.builders.identifiers import next_id


@dataclass(frozen=True)
class ParticipantContextBuilder:
    """Diego, a member, first in the round, joining the room as ``str(user_id)``."""

    user_id: UUID = field(default_factory=next_id)
    name: str = "Diego"
    role: TeamRole = TeamRole.MEMBER
    turn_order: int = 1

    def named(self, name: str) -> Self:
        return replace(self, name=name)

    def as_admin(self) -> Self:
        return replace(self, role=TeamRole.ADMIN)

    def in_turn(self, turn_order: int) -> Self:
        return replace(self, turn_order=turn_order)

    def build(self) -> ParticipantContext:
        return ParticipantContext(
            user_id=self.user_id,
            name=self.name,
            room_identity=str(self.user_id),
            role=self.role,
            turn_order=self.turn_order,
        )
