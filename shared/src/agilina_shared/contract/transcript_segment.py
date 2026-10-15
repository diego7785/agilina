from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from agilina_shared.contract.contract_model import ContractModel


class TranscriptSegment(ContractModel):
    """A final transcript fragment attributed to whoever said it.

    The attribution is not computed by acoustic analysis: the identity arrives
    signed in the audio track token.
    """

    user_id: UUID
    room_identity: str
    text: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _ends_after_it_starts(self) -> Self:
        # The database refuses it too (transcript_segment_times_ordered): here it is a 422.
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms must not be before start_ms")
        return self
