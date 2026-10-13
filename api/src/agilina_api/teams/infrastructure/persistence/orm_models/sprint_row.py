from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Date, DateTime, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from agilina_api.shared.infrastructure.database.base import Base
from agilina_api.shared.infrastructure.database.types import pg_enum
from agilina_api.teams.domain.sprint import SprintStatus


class SprintRow(Base):
    __tablename__ = "sprint"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    team_id: Mapped[UUID] = mapped_column(Uuid)
    number: Mapped[int] = mapped_column(Integer)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    status: Mapped[SprintStatus] = mapped_column(pg_enum(SprintStatus, "sprint_status"))
    daily_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    daily_time_zone: Mapped[str] = mapped_column(Text)
