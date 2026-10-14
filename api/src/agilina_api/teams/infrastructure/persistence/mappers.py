"""Translate between the sprint's ORM rows and the ``Sprint`` aggregate, in both directions."""

from collections.abc import Sequence
from uuid import UUID

from agilina_api.teams.domain.sprint import DailyTime, Sprint, SprintPeriod
from agilina_api.teams.infrastructure.persistence.orm_models import (
    SprintParticipantRow,
    SprintRow,
)


def sprint_to_domain(row: SprintRow, participants: Sequence[UUID]) -> Sprint:
    """``participants`` are the participants' ``user_id`` in turn order."""
    return Sprint(
        sprint_id=row.id,
        team_id=row.team_id,
        number=row.number,
        period=SprintPeriod(start=row.start_date, end=row.end_date),
        daily_time=DailyTime(at=row.daily_time_utc, time_zone=row.daily_time_zone),
        participants=participants,
        status=row.status,
    )


def sprint_to_row(sprint: Sprint) -> SprintRow:
    return SprintRow(
        id=sprint.id,
        team_id=sprint.team_id,
        number=sprint.number,
        start_date=sprint.period.start,
        end_date=sprint.period.end,
        status=sprint.status,
        daily_time_utc=sprint.daily_time.at,
        daily_time_zone=sprint.daily_time.time_zone,
    )


def participants_to_rows(sprint: Sprint) -> list[SprintParticipantRow]:
    """One row per participant, with ``turn_order`` from 1 in the order of the list."""
    return [
        SprintParticipantRow(
            sprint_id=sprint.id, team_id=sprint.team_id, user_id=user_id, turn_order=position
        )
        for position, user_id in enumerate(sprint.participants, start=1)
    ]
