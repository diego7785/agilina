"""SQLAlchemy repository of the ``Ceremony`` aggregate and the result it receives."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agilina_api.ceremonies.application.ports.outbound import CeremonyRepository
from agilina_api.ceremonies.domain.ceremony import Ceremony
from agilina_api.ceremonies.domain.errors import ResultAlreadyReceivedError
from agilina_api.ceremonies.infrastructure.persistence.orm_models import (
    CeremonyEventRow,
    CeremonyResultRow,
    CeremonyRow,
    TranscriptSegmentRow,
)
from agilina_api.shared.infrastructure.database.types import violated_constraint
from agilina_shared import CeremonyResult

RESULT_PRIMARY_KEY = "ceremony_result_pkey"
OCCURRENCE_UNIQUE = "ceremony_occurrence_unique"


class SqlAlchemyCeremonyRepository(CeremonyRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_or_get(self, ceremony: Ceremony) -> Ceremony:
        """Insert the ceremony or, when its occurrence already has one, read that one.

        ``ON CONFLICT DO NOTHING`` on ``ceremony_occurrence_unique`` makes the second of two
        concurrent inserts wait for the first and then insert nothing; its next statement sees
        the committed row (READ COMMITTED), so both get the same ceremony.
        """
        inserted = (
            await self._session.execute(
                insert(CeremonyRow)
                .values(
                    id=ceremony.id,
                    team_id=ceremony.team_id,
                    sprint_id=ceremony.sprint_id,
                    scheduled_at=ceremony.scheduled_at,
                )
                .on_conflict_do_nothing(constraint=OCCURRENCE_UNIQUE)
                .returning(CeremonyRow.id)
            )
        ).scalar_one_or_none()
        if inserted is not None:
            return ceremony
        stored_id, digest = (
            await self._session.execute(
                select(CeremonyRow.id, CeremonyResultRow.payload_sha256)
                .outerjoin(CeremonyResultRow, CeremonyResultRow.ceremony_id == CeremonyRow.id)
                .where(
                    CeremonyRow.team_id == ceremony.team_id,
                    CeremonyRow.sprint_id == ceremony.sprint_id,
                    CeremonyRow.scheduled_at == ceremony.scheduled_at,
                )
            )
        ).one()
        return Ceremony(
            ceremony_id=stored_id,
            team_id=ceremony.team_id,
            sprint_id=ceremony.sprint_id,
            scheduled_at=ceremony.scheduled_at,
            result_digest=digest,
        )

    async def lock(self, ceremony_id: UUID) -> Ceremony | None:
        """Load the ceremony and **lock its row** until the transaction ends.

        The lock serializes two deliveries of the same ceremony: the second waits for the first
        and then reads the digest it committed.
        """
        row = (
            await self._session.execute(
                select(CeremonyRow).where(CeremonyRow.id == ceremony_id).with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        digest = (
            await self._session.execute(
                select(CeremonyResultRow.payload_sha256).where(
                    CeremonyResultRow.ceremony_id == ceremony_id
                )
            )
        ).scalar_one_or_none()
        return Ceremony(
            ceremony_id=row.id,
            team_id=row.team_id,
            sprint_id=row.sprint_id,
            scheduled_at=row.scheduled_at,
            result_digest=digest,
        )

    async def add_result(
        self, ceremony: Ceremony, result: CeremonyResult, *, received_at: datetime
    ) -> None:
        if ceremony.result_digest is None:
            raise ValueError(f"Ceremony {ceremony.id} has received no result to store")
        self._session.add(
            CeremonyResultRow(
                ceremony_id=ceremony.id,
                team_id=ceremony.team_id,
                status=result.status,
                started_at=result.started_at,
                closed_at=result.closed_at,
                present_participants=list(result.present_participants),
                absent_participants=list(result.absent_participants),
                degraded=result.degraded,
                degradation_detail=result.degradation_detail,
                payload_sha256=ceremony.result_digest,
                received_at=received_at,
            )
        )
        try:
            await self._session.flush()  # the result row must exist before its segments
        except IntegrityError as error:
            # Only when the lock was not taken: the row lock makes the second delivery wait.
            if violated_constraint(error) == RESULT_PRIMARY_KEY:
                raise ResultAlreadyReceivedError(
                    f"Ceremony {ceremony.id} already has another result"
                ) from error
            raise
        self._session.add_all(
            TranscriptSegmentRow(
                id=uuid4(),
                ceremony_id=ceremony.id,
                team_id=ceremony.team_id,
                position=position,
                user_id=segment.user_id,
                text=segment.text,
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
            )
            for position, segment in enumerate(result.segments)
        )
        self._session.add_all(
            CeremonyEventRow(
                id=uuid4(),
                ceremony_id=ceremony.id,
                team_id=ceremony.team_id,
                position=position,
                type=event.type,
                at=event.at,
                user_id=event.user_id,
            )
            for position, event in enumerate(result.events)
        )
        await self._session.flush()
