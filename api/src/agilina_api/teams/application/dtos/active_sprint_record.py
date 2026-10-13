from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID


@dataclass(frozen=True)
class ActiveSprintRecord:
    """A team's active sprint as it is stored (HU-07)."""

    sprint_id: UUID
    number: int
    """The sprint's number in its team (the 12 of "Sprint 12"), assigned when it was saved."""
    start_date: date
    end_date: date
    daily_time: datetime
    """The daily's UTC anchor instant (AD-31)."""
    time_zone: str
    """The IANA time zone the daily's time was captured in."""
    participants: tuple[UUID, ...]
    """The ``app_user`` ids of the daily's participants, in turn order."""
