from datetime import datetime
from uuid import UUID

from pydantic import Field

from agilina_shared.contract.contract_model import ContractModel
from agilina_shared.enums import CeremonyEventType


class CeremonyEvent(ContractModel):
    """Something that happened in the ceremony, in the order the worker saw it."""

    type: CeremonyEventType
    at: datetime = Field(description="Always in UTC.")
    user_id: UUID | None = Field(
        default=None,
        description="The participant the event is about (a turn); none for the ceremony itself.",
    )
