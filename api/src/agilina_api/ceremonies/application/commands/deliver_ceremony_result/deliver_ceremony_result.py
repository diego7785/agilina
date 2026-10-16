from dataclasses import dataclass
from uuid import UUID

from agilina_shared import CeremonyResult


@dataclass(frozen=True)
class DeliverCeremonyResult:
    ceremony_id: UUID
    """The ceremony the result is delivered to (the route's)."""
    result: CeremonyResult
    """The shared contract as it is: the result is stored from it, not copied into another
    model."""
