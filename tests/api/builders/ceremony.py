"""Builders of what the ceremonies read: ``CeremonyRecord`` and ``RosterRecord`` (AGI-64)."""

from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Self
from uuid import UUID

from agilina_api.ceremonies.application.dtos import (
    CeremonyRecord,
    RosterParticipant,
    RosterRecord,
)
from agilina_api.teams.domain.sprint import Sprint
from agilina_shared.enums import Language, OperationMode, TeamRole
from tests.api.builders.defaults import DAILY_TIME, DAILY_TIME_ZONE, SPRINT_END, SPRINT_START
from tests.api.builders.identifiers import next_id


@dataclass(frozen=True)
class CeremonyBuilder:
    """A ceremony scheduled at the default daily (2026-10-05T14:00Z, day 1 of the default
    sprint). ``for_sprint(sprint)`` puts it in that sprint of that sprint's team.

    No behavior creates ceremonies yet (AGI-59): ``build()`` is the record as stored, and
    ``tests/api/integration/support.py::stored_ceremony`` writes its row."""

    ceremony_id: UUID = field(default_factory=next_id)
    team_id: UUID = field(default_factory=next_id)
    sprint_id: UUID = field(default_factory=next_id)
    scheduled_at: datetime = DAILY_TIME

    def with_id(self, ceremony_id: UUID) -> Self:
        return replace(self, ceremony_id=ceremony_id)

    def for_sprint(self, sprint: Sprint) -> Self:
        return replace(self, team_id=sprint.team_id, sprint_id=sprint.id)

    def for_team_and_sprint(self, team_id: UUID, sprint_id: UUID) -> Self:
        return replace(self, team_id=team_id, sprint_id=sprint_id)

    def scheduled_at_instant(self, instant: datetime) -> Self:
        return replace(self, scheduled_at=instant)

    def build(self) -> CeremonyRecord:
        return CeremonyRecord(
            team_id=self.team_id, sprint_id=self.sprint_id, scheduled_at=self.scheduled_at
        )


@dataclass(frozen=True)
class RosterBuilder:
    """A team in English and support mode, with the default sprint's calendar (2026-10-05 to
    2026-10-16 in America/Bogota) and no participant. ``with_participant`` adds one at the
    next turn."""

    language: Language = Language.EN
    mode: OperationMode = OperationMode.SUPPORT
    start: date = SPRINT_START
    end: date = SPRINT_END
    time_zone: str = DAILY_TIME_ZONE
    participants: tuple[RosterParticipant, ...] = ()

    def in_language(self, language: Language) -> Self:
        return replace(self, language=language)

    def in_mode(self, mode: OperationMode) -> Self:
        return replace(self, mode=mode)

    def with_time_zone(self, time_zone: str) -> Self:
        return replace(self, time_zone=time_zone)

    def with_participant(self, user_id: UUID, role: TeamRole = TeamRole.MEMBER) -> Self:
        turn = len(self.participants) + 1
        participant = RosterParticipant(user_id=user_id, role=role, turn_order=turn)
        return replace(self, participants=(*self.participants, participant))

    def build(self) -> RosterRecord:
        return RosterRecord(
            language=self.language,
            mode=self.mode,
            start_date=self.start,
            end_date=self.end,
            time_zone=self.time_zone,
            participants=self.participants,
        )
