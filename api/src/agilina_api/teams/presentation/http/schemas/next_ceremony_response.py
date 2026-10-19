from datetime import datetime

from pydantic import BaseModel, Field

from agilina_shared.enums import CeremonyType


class NextCeremonyResponse(BaseModel):
    type: CeremonyType = Field(description="Only the daily exists for now.")
    starts_at: datetime = Field(description="When the ceremony starts, in UTC.")
    join_opens_at: datetime = Field(
        description=(
            "From when a participant may join the room, in UTC: ten minutes before `starts_at`."
        )
    )
    join_closes_at: datetime = Field(
        description=(
            "Until when a participant may join the room, in UTC (not included): fifteen minutes "
            "after `starts_at`, so that whoever arrives late can still join. Until then this "
            "ceremony is the one the dashboard shows, even if it has started."
        )
    )
