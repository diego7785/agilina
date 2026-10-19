from collections.abc import Sequence
from datetime import datetime

from agilina_shared.sprint_calendar.join_closes_at import join_closes_at


def joinable_daily_at(occurrences: Sequence[datetime], now: datetime) -> datetime | None:
    """The first daily whose window to join has not closed at ``now``, or ``None`` when none is
    left.

    It is the daily under way during its first ``JOIN_WINDOW_TAIL``, so that a participant who
    arrives late still finds its room, and otherwise the next one. ``occurrences`` come in
    chronological order, as ``daily_occurrences`` returns them; ``now`` is in UTC (AD-20). The API
    shows this daily on the dashboard and issues the token of its room with the same rule, so the
    button and the room never disagree.
    """
    return next(
        (occurrence for occurrence in occurrences if join_closes_at(occurrence) > now), None
    )
