"""Builder of ``Sprint`` (HU-07)."""

from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Protocol, Self
from uuid import UUID

from agilina_api.teams.domain.sprint import DailyTime, Sprint, SprintPeriod, SprintStatus
from agilina_api.teams.domain.team import Team
from tests.api.builders.defaults import (
    DAILY_TIME,
    DAILY_TIME_ZONE,
    SPRINT_END,
    SPRINT_START,
)
from tests.api.builders.identifiers import next_id


@dataclass(frozen=True)
class SprintBuilder:
    """Sprint number 1, active, from Monday 2026-10-05 to Friday 2026-10-16 (12 calendar days), with
    the daily at 09:00 in America/Bogota (the anchor 2026-10-05T14:00Z) and no participants.

    ``for_team(team)`` takes the team's active members, in the order they joined, as the
    daily's participants. ``closed()`` and ``planned()`` restore a sprint in that status: no
    behavior reaches them yet (closing a sprint is HU-10). Every sprint is rebuilt as stored.
    """

    sprint_id: UUID = field(default_factory=next_id)
    team_id: UUID = field(default_factory=next_id)
    number: int = 1
    start: date = SPRINT_START
    end: date = SPRINT_END
    daily_at: datetime = DAILY_TIME
    time_zone: str = DAILY_TIME_ZONE
    participants: tuple[UUID, ...] = ()
    status: SprintStatus = SprintStatus.ACTIVE

    def with_id(self, sprint_id: UUID) -> Self:
        return replace(self, sprint_id=sprint_id)

    def for_team(self, team: Team) -> Self:
        """A sprint of ``team``, with its active members as the daily's participants."""
        members = tuple(m.user_id for m in team.memberships if m.is_active)
        return replace(self, team_id=team.id, participants=members)

    def numbered(self, number: int) -> Self:
        """The sprint's number in its team (1 unless said otherwise)."""
        return replace(self, number=number)

    def for_team_id(self, team_id: UUID) -> Self:
        """A sprint of the team ``team_id``; the participants stay as they are."""
        return replace(self, team_id=team_id)

    def with_period(self, start: date, end: date) -> Self:
        return replace(self, start=start, end=end)

    def with_daily_time(self, at: datetime, time_zone: str) -> Self:
        return replace(self, daily_at=at, time_zone=time_zone)

    def with_participants(self, *user_ids: UUID) -> Self:
        """The daily's participants, in turn order."""
        return replace(self, participants=user_ids)

    def closed(self) -> Self:
        return replace(self, status=SprintStatus.CLOSED)

    def planned(self) -> Self:
        return replace(self, status=SprintStatus.PLANNED)

    def build(self) -> Sprint:
        """The sprint as stored, restored with no participant rule checked again: a sprint
        whose daily was left with no participant, or with someone who later left the team,
        can be built too. The rules of ``Sprint.start`` are tested on it, not here."""
        return Sprint(
            sprint_id=self.sprint_id,
            team_id=self.team_id,
            number=self.number,
            period=SprintPeriod(start=self.start, end=self.end),
            daily_time=DailyTime(at=self.daily_at, time_zone=self.time_zone),
            participants=self.participants,
            status=self.status,
        )

    async def saved_in(self, repository: "SprintStore") -> Sprint:
        sprint = self.build()
        await repository.add(sprint)
        return sprint


class SprintStore(Protocol):
    async def add(self, sprint: Sprint) -> None: ...
