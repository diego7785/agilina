from datetime import datetime

from pydantic import BaseModel, Field


class RoomAdmissionResponse(BaseModel):
    room_name: str = Field(
        description="The LiveKit room of today's daily: `<tenant>-<ceremony_id>`, a new one "
        "for each daily."
    )
    token: str = Field(
        description="The LiveKit access token: it lets only this user into only this room, "
        "publishing their microphone and listening to the others."
    )
    expires_at: datetime = Field(description="When the token stops letting its bearer in, in UTC.")
    livekit_url: str = Field(description="The LiveKit server the client connects to.")
