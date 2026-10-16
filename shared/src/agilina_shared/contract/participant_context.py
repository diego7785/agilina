from uuid import UUID

from pydantic import Field

from agilina_shared.contract.contract_model import ContractModel
from agilina_shared.enums import TeamRole


class ParticipantContext(ContractModel):
    """Who takes part in the ceremony and in which order their turn comes."""

    user_id: UUID
    name: str
    room_identity: str = Field(
        description="Identity the participant uses to join LiveKit, always str(user_id); "
        "it is the one the worker uses to attribute what is said."
    )
    role: TeamRole
    turn_order: int = Field(ge=1, description="Position in the round, from 1.")
