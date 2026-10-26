from pydantic import BaseModel, Field

from agilina_api.ceremonies.presentation.http.schemas.daily_participant_response import (
    DailyParticipantResponse,
)


class DailyParticipantsResponse(BaseModel):
    participants: list[DailyParticipantResponse] = Field(
        description="The participants of the active sprint's daily, in turn order."
    )
