from collections.abc import Sequence
from datetime import datetime


def next_daily_at(occurrences: Sequence[datetime], now: datetime) -> datetime | None:
    """The first occurrence of the daily at or after ``now``, or ``None`` when none is left.

    ``occurrences`` come in chronological order, as ``daily_occurrences`` returns them. The daily
    that is starting at this very instant is still the next one; one instant later it is the day
    after's. The caller takes ``now`` from its ``Clock`` in UTC (AD-20).
    """
    return next((occurrence for occurrence in occurrences if occurrence >= now), None)
