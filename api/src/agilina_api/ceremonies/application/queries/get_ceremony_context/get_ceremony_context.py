from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class GetCeremonyContext:
    tenant: str
    """The slug of the tenant the request named: the context carries it, the database does
    not hold it (AD-29)."""
    ceremony_id: UUID
