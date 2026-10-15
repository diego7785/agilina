from datetime import datetime
from uuid import UUID

from pydantic import Field

from agilina_shared.contract.ceremony_event import CeremonyEvent
from agilina_shared.contract.contract_model import ContractModel
from agilina_shared.contract.transcript_segment import TranscriptSegment
from agilina_shared.enums import CeremonyStatus


class CeremonyResult(ContractModel):
    """What the worker hands to the API when the ceremony closes.

    No reasoning happens here: the worker delivers the full attributed
    transcript and the API processes it once, outside the latency-critical
    path (AD-19).
    """

    ceremony_id: UUID
    status: CeremonyStatus
    started_at: datetime = Field(description="Always in UTC.")
    closed_at: datetime = Field(description="Always in UTC.")
    present_participants: list[UUID]
    absent_participants: list[UUID] = Field(default_factory=list)
    segments: list[TranscriptSegment]
    events: list[CeremonyEvent] = Field(
        description="What happened in the ceremony, in order; it may be empty."
    )
    degraded: bool = Field(
        default=False,
        description="True when the transcription service did not respond and the "
        "ceremony went on without automatic facilitation.",
    )
    degradation_detail: str | None = None
