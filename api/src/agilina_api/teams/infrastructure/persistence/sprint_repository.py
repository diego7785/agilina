"""SQLAlchemy repository of the ``Sprint`` aggregate, with its participants."""

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agilina_api.shared.infrastructure.database.types import violated_constraint
from agilina_api.teams.domain.errors import ActiveSprintExistsError
from agilina_api.teams.domain.repositories import SprintRepository
from agilina_api.teams.domain.sprint import Sprint
from agilina_api.teams.infrastructure.persistence.mappers import (
    participants_to_rows,
    sprint_to_domain,
    sprint_to_row,
)
from agilina_api.teams.infrastructure.persistence.orm_models import (
    SprintParticipantRow,
    SprintRow,
)
from agilina_api.teams.infrastructure.persistence.sprint_queries import (
    is_active_sprint_of,
    participants_of,
)

ONE_ACTIVE_PER_TEAM = "sprint_one_active_per_team"
NUMBER_PER_TEAM = "sprint_number_unique"


class SqlAlchemySprintRepository(SprintRepository):
    """It does not lock the sprint: every use case that changes one loads (and locks) its
    team first, so two changes to the same team's sprint never interleave."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, sprint: Sprint) -> None:
        """Insert the sprint and its participants.

        ``StartSprint`` asks first whether the team has an active sprint, under the team's
        lock; should a second active one still reach the database, the
        ``sprint_one_active_per_team`` index refuses it and the repository answers the same
        ``ActiveSprintExistsError``. Any other violation is not the domain's and goes up as
        it is.
        """
        self._session.add(sprint_to_row(sprint))
        try:
            await self._session.flush()  # the sprint row must exist before its participants
            self._session.add_all(participants_to_rows(sprint))
            await self._session.flush()
        except IntegrityError as error:
            if violated_constraint(error) in {ONE_ACTIVE_PER_TEAM, NUMBER_PER_TEAM}:
                raise ActiveSprintExistsError(
                    f"Team {sprint.team_id} already has an active sprint"
                ) from error
            raise

    async def next_number(self, team_id: UUID) -> int:
        statement = select(func.coalesce(func.max(SprintRow.number), 0) + 1).where(
            SprintRow.team_id == team_id
        )
        return int((await self._session.execute(statement)).scalar_one())

    async def get_active(self, team_id: UUID) -> Sprint | None:
        row = (
            await self._session.execute(select(SprintRow).where(is_active_sprint_of(team_id)))
        ).scalar_one_or_none()
        if row is None:
            return None
        return sprint_to_domain(row, await participants_of(self._session, row.id))

    async def save(self, sprint: Sprint) -> None:
        """Write the columns the aggregate knows and replace its participants.

        The participants are deleted and inserted again, in that order and in separate
        statements: rewriting the turn orders in place would collide with the
        ``(sprint_id, turn_order)`` unique constraint halfway through.
        """
        row = await self._session.get(SprintRow, sprint.id)
        if row is None:
            raise LookupError(f"Sprint {sprint.id} does not exist")
        row.start_date, row.end_date = sprint.period.start, sprint.period.end
        row.daily_time_utc = sprint.daily_time.at
        row.daily_time_zone = sprint.daily_time.time_zone
        row.status = sprint.status
        await self._session.execute(
            delete(SprintParticipantRow).where(SprintParticipantRow.sprint_id == sprint.id)
        )
        self._session.add_all(participants_to_rows(sprint))
        await self._session.flush()
