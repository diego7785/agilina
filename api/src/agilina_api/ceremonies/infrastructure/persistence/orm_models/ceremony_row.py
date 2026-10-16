from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from agilina_api.shared.infrastructure.database.base import Base


class CeremonyRow(Base):
    __tablename__ = "ceremony"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    team_id: Mapped[UUID] = mapped_column(Uuid)
    sprint_id: Mapped[UUID] = mapped_column(Uuid)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
