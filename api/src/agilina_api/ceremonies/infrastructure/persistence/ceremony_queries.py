"""Read side of the ceremonies (CQRS): straight SQL, no aggregate."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agilina_api.ceremonies.application.dtos import CeremonyRecord
from agilina_api.ceremonies.application.ports.outbound import CeremonyQueries
from agilina_api.ceremonies.infrastructure.persistence.orm_models import CeremonyRow


class SqlCeremonyQueries(CeremonyQueries):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def ceremony_of(self, ceremony_id: UUID) -> CeremonyRecord | None:
        statement = select(
            CeremonyRow.team_id, CeremonyRow.sprint_id, CeremonyRow.scheduled_at
        ).where(CeremonyRow.id == ceremony_id)
        async with self._session_factory() as session:
            row = (await session.execute(statement)).one_or_none()
        if row is None:
            return None
        return CeremonyRecord(
            team_id=row.team_id, sprint_id=row.sprint_id, scheduled_at=row.scheduled_at
        )
