"""Builder of ``CeremonyEvent``."""

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Self
from uuid import UUID

from agilina_shared.contract import CeremonyEvent
from agilina_shared.enums import CeremonyEventType
from tests.shared.builders.defaults import STARTED_AT


@dataclass(frozen=True)
class CeremonyEventBuilder:
    """The ceremony started, at the moment it was scheduled; it is about nobody in particular."""

    type: CeremonyEventType = CeremonyEventType.CEREMONY_STARTED
    at: datetime = STARTED_AT
    user_id: UUID | None = None

    def of_type(self, event_type: CeremonyEventType) -> Self:
        return replace(self, type=event_type)

    def about(self, user_id: UUID) -> Self:
        return replace(self, user_id=user_id)

    def happened_at(self, instant: datetime) -> Self:
        return replace(self, at=instant)

    def build(self) -> CeremonyEvent:
        return CeremonyEvent(type=self.type, at=self.at, user_id=self.user_id)
