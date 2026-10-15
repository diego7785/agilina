from uuid import UUID

from sqlalchemy import Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from agilina_api.shared.infrastructure.database.base import Base


class TranscriptSegmentRow(Base):
    __tablename__ = "transcript_segment"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    ceremony_id: Mapped[UUID] = mapped_column(Uuid)
    team_id: Mapped[UUID] = mapped_column(Uuid)
    position: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[UUID] = mapped_column(Uuid)
    text: Mapped[str] = mapped_column(Text)
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
