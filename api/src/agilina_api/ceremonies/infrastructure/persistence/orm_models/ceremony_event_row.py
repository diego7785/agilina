from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from agilina_api.shared.infrastructure.database.base import Base
from agilina_api.shared.infrastructure.database.types import pg_enum
from agilina_shared.enums import CeremonyEventType


class CeremonyEventRow(Base):
    __tablename__ = "ceremony_event"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    ceremony_id: Mapped[UUID] = mapped_column(Uuid)
    team_id: Mapped[UUID] = mapped_column(Uuid)
    position: Mapped[int] = mapped_column(Integer)
    type: Mapped[CeremonyEventType] = mapped_column(
        pg_enum(CeremonyEventType, "ceremony_event_type")
    )
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
