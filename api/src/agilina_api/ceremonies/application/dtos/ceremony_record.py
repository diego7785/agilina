from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class CeremonyRecord:
    """A ceremony as it is stored: whose it is and when it is scheduled."""

    team_id: UUID
    sprint_id: UUID
    scheduled_at: datetime
    """The instant the ceremony is scheduled, in UTC."""
