from dataclasses import dataclass
from datetime import datetime

from agilina_api.teams.application.dtos.active_sprint_record import ActiveSprintRecord
from agilina_shared.sprint_calendar import SprintDay


@dataclass(frozen=True)
class ActiveSprintView:
    """The active sprint with what is computed from it at the current instant: the day N of M,
    the next daily (HU-07, acceptance criterion 6) and the daily whose room one may join
    (AGI-60)."""

    sprint: ActiveSprintRecord
    day: SprintDay
    next_daily_at: datetime | None
    """The first occurrence of the daily at or after the current instant, in UTC; ``None``
    once the sprint's last daily has started."""
    joinable_daily_at: datetime | None
    """The first daily whose window to join has not closed, in UTC: the one under way during its
    first minutes, so that whoever arrives late still finds its room, or else the next one.
    ``None`` once the window of the sprint's last daily has closed."""
