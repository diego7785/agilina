from collections.abc import Sequence
from datetime import datetime, timedelta

from agilina_shared.sprint_calendar.join_opens_at import join_opens_at

DAILY_JOIN_GRACE = timedelta(hours=1)
"""How long after a daily starts a participant who arrives late may still join it."""


def current_daily_at(occurrences: Sequence[datetime], now: datetime) -> datetime | None:
    """The occurrence of the daily whose window to join holds ``now``, or ``None``.

    The window goes from ``join_opens_at(occurrence)`` (included) to the occurrence plus
    ``DAILY_JOIN_GRACE`` (excluded). Two windows never overlap, as dailies are a day apart, so
    at most one occurrence matches. The caller takes ``now`` from its ``Clock`` in UTC (AD-20).
    """
    return next(
        (
            occurrence
            for occurrence in occurrences
            if join_opens_at(occurrence) <= now < occurrence + DAILY_JOIN_GRACE
        ),
        None,
    )
