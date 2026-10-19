"""Builders of what the ceremonies read: ``CeremonyRecord`` and ``RosterRecord`` (AGI-64)."""

from dataclasses import dataclass, field, replace
from datetime import date, datetime, time
from typing import Self
from uuid import UUID

from agilina_api.ceremonies.application.dtos import (
    CeremonyRecord,
    RosterParticipant,
    RosterRecord,
)
from agilina_api.ceremonies.domain.ceremony import Ceremony
from agilina_api.teams.domain.sprint import Sprint
from agilina_shared.enums import Language, OperationMode, TeamRole
from tests.api.builders.defaults import (
    DAILY_LOCAL_TIME,
    DAILY_TIME,
    DAILY_TIME_ZONE,
    SPRINT_END,
    SPRINT_START,
)
from tests.api.builders.identifiers import next_id


@dataclass(frozen=True)
class CeremonyBuilder:
    """A ceremony scheduled at the default daily (2026-10-05T14:00Z, day 1 of the default
    sprint). ``for_sprint(sprint)`` puts it in that sprint of that sprint's team.

    ``build()`` is the record as stored, and ``tests/api/integration/support.py::stored_ceremony``
    writes its row. ``aggregate()`` is the ``Ceremony`` the commands work on, with the result
    ``with_result_received`` gave it."""

    ceremony_id: UUID = field(default_factory=next_id)
    team_id: UUID = field(default_factory=next_id)
    sprint_id: UUID = field(default_factory=next_id)
    scheduled_at: datetime = DAILY_TIME
    result_digest: str | None = None

    def with_id(self, ceremony_id: UUID) -> Self:
        return replace(self, ceremony_id=ceremony_id)

    def for_sprint(self, sprint: Sprint) -> Self:
        return replace(self, team_id=sprint.team_id, sprint_id=sprint.id)

    def for_team_and_sprint(self, team_id: UUID, sprint_id: UUID) -> Self:
        return replace(self, team_id=team_id, sprint_id=sprint_id)

    def scheduled_at_instant(self, instant: datetime) -> Self:
        return replace(self, scheduled_at=instant)

    def with_result_received(self, digest: str) -> Self:
        return replace(self, result_digest=digest)

    def aggregate(self) -> Ceremony:
        """The ceremony, without a result or with the one it received through
        ``Ceremony.receive_result`` (nobody spoke in it)."""
        ceremony = Ceremony(
            ceremony_id=self.ceremony_id,
            team_id=self.team_id,
            sprint_id=self.sprint_id,
            scheduled_at=self.scheduled_at,
            result_digest=None,
        )
        if self.result_digest is not None:
            ceremony.receive_result(self.result_digest, {}, ())
        return ceremony

    def build(self) -> CeremonyRecord:
        return CeremonyRecord(
            team_id=self.team_id, sprint_id=self.sprint_id, scheduled_at=self.scheduled_at
        )


@dataclass(frozen=True)
class RosterBuilder:
    """A team in English and support mode, with the default sprint's calendar (2026-10-05 to
    2026-10-16 in America/Bogota, daily at 09:00) and no participant. ``with_participant`` adds
    one at the next turn."""

    sprint_id: UUID = field(default_factory=next_id)
    language: Language = Language.EN
    mode: OperationMode = OperationMode.SUPPORT
    start: date = SPRINT_START
    end: date = SPRINT_END
    daily_time: time = DAILY_LOCAL_TIME
    time_zone: str = DAILY_TIME_ZONE
    participants: tuple[RosterParticipant, ...] = ()

    def in_language(self, language: Language) -> Self:
        return replace(self, language=language)

    def in_mode(self, mode: OperationMode) -> Self:
        return replace(self, mode=mode)

    def for_sprint_id(self, sprint_id: UUID) -> Self:
        return replace(self, sprint_id=sprint_id)

    def with_daily_time(self, daily_time: time) -> Self:
        return replace(self, daily_time=daily_time)

    def with_time_zone(self, time_zone: str) -> Self:
        return replace(self, time_zone=time_zone)

    def with_participant(self, user_id: UUID, role: TeamRole = TeamRole.MEMBER) -> Self:
        turn = len(self.participants) + 1
        participant = RosterParticipant(user_id=user_id, role=role, turn_order=turn)
        return replace(self, participants=(*self.participants, participant))

    def build(self) -> RosterRecord:
        return RosterRecord(
            sprint_id=self.sprint_id,
            language=self.language,
            mode=self.mode,
            start_date=self.start,
            end_date=self.end,
            daily_time=self.daily_time,
            time_zone=self.time_zone,
            participants=self.participants,
        )
