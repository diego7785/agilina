from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Text, Uuid
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from agilina_api.shared.infrastructure.database.base import Base
from agilina_api.shared.infrastructure.database.types import pg_enum
from agilina_shared.enums import CeremonyStatus


class CeremonyResultRow(Base):
    __tablename__ = "ceremony_result"

    ceremony_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    team_id: Mapped[UUID] = mapped_column(Uuid)
    status: Mapped[CeremonyStatus] = mapped_column(pg_enum(CeremonyStatus, "ceremony_status"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    present_participants: Mapped[list[UUID]] = mapped_column(ARRAY(Uuid))
    absent_participants: Mapped[list[UUID]] = mapped_column(ARRAY(Uuid))
    degraded: Mapped[bool] = mapped_column(Boolean)
    degradation_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_sha256: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
