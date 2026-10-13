from datetime import datetime

from pydantic import BaseModel, Field

from agilina_shared.enums import CeremonyType


class NextCeremonyResponse(BaseModel):
    type: CeremonyType = Field(description="Only the daily exists for now.")
    starts_at: datetime = Field(description="When the ceremony starts, in UTC.")
    join_opens_at: datetime = Field(
        description=(
            "From when a participant may join the room, in UTC: ten minutes before `starts_at`. "
            "The window goes from this instant to `starts_at`; the ceremony as a record (when "
            "it started and ended) arrives with its own stories."
        )
    )
