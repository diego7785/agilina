from pydantic import BaseModel, Field


class DailyParticipantResponse(BaseModel):
    room_identity: str = Field(
        description="The identity the participant carries in the LiveKit room: `str(user_id)`."
    )
    full_name: str = Field(description="The participant's full name.")
    email: str = Field(description="The participant's email.")
