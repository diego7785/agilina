"""Builder of ``CeremonyContext``."""

from dataclasses import dataclass, field, replace
from typing import Self
from uuid import UUID

from agilina_shared import room_name_for
from agilina_shared.contract import CeremonyContext, ParticipantContext
from agilina_shared.enums import Language, OperationMode
from tests.shared.builders.defaults import TENANT
from tests.shared.builders.identifiers import next_id
from tests.shared.builders.participant_context import ParticipantContextBuilder


def _two_participants() -> tuple[ParticipantContext, ...]:
    return (
        ParticipantContextBuilder().named("Diego").as_admin().in_turn(1).build(),
        ParticipantContextBuilder().named("Angélica").in_turn(2).build(),
    )


@dataclass(frozen=True)
class CeremonyContextBuilder:
    """The daily of acme on day 3 of 15, in Spanish and in support mode, with two people.

    The room is named by the shared convention, so it always matches tenant and ceremony.
    """

    tenant: str = TENANT
    ceremony_id: UUID = field(default_factory=next_id)
    team_id: UUID = field(default_factory=next_id)
    sprint_id: UUID = field(default_factory=next_id)
    language: Language = Language.ES
    mode: OperationMode = OperationMode.SUPPORT
    sprint_day: int = 3
    sprint_total_days: int = 15
    participants: tuple[ParticipantContext, ...] = field(default_factory=_two_participants)

    def for_tenant(self, tenant: str) -> Self:
        return replace(self, tenant=tenant)

    def in_language(self, language: Language) -> Self:
        return replace(self, language=language)

    def with_participants(self, *participants: ParticipantContext) -> Self:
        return replace(self, participants=participants)

    def build(self) -> CeremonyContext:
        return CeremonyContext(
            tenant=self.tenant,
            ceremony_id=self.ceremony_id,
            team_id=self.team_id,
            sprint_id=self.sprint_id,
            room=room_name_for(self.tenant, self.ceremony_id),
            language=self.language,
            mode=self.mode,
            sprint_day=self.sprint_day,
            sprint_total_days=self.sprint_total_days,
            participants=list(self.participants),
        )
