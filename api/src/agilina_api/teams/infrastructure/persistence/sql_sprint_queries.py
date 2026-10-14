"""Read side of the sprint (CQRS): the team's active sprint, straight SQL, no aggregate."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agilina_api.teams.application.dtos import ActiveSprintRecord
from agilina_api.teams.application.ports.outbound import SprintQueries
from agilina_api.teams.infrastructure.persistence.orm_models import (
    SprintParticipantRow,
    SprintRow,
)
from agilina_api.teams.infrastructure.persistence.sprint_queries import is_active_sprint_of


class SqlSprintQueries(SprintQueries):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def active_sprint_of(self, team_id: UUID) -> ActiveSprintRecord | None:
        """One statement for the sprint and its participants, so the read is a single
        snapshot: an edit committed halfway cannot mix the old sprint with the new
        participants. One row per participant, in turn order; a sprint left with no
        participant comes back as one row with no ``user_id``."""
        statement = (
            select(
                SprintRow.id,
                SprintRow.number,
                SprintRow.start_date,
                SprintRow.end_date,
                SprintRow.daily_time_utc,
                SprintRow.daily_time_zone,
                SprintParticipantRow.user_id,
            )
            .outerjoin(SprintParticipantRow, SprintParticipantRow.sprint_id == SprintRow.id)
            .where(is_active_sprint_of(team_id))
            .order_by(SprintParticipantRow.turn_order)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
        if not rows:
            return None
        sprint = rows[0]
        return ActiveSprintRecord(
            sprint_id=sprint.id,
            number=sprint.number,
            start_date=sprint.start_date,
            end_date=sprint.end_date,
            daily_time=sprint.daily_time_utc,
            time_zone=sprint.daily_time_zone,
            participants=tuple(row.user_id for row in rows if row.user_id is not None),
        )
