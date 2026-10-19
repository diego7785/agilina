from datetime import datetime, timedelta

JOIN_WINDOW_TAIL = timedelta(minutes=15)
"""How long after a ceremony starts its participants may still join the room: the timebox of
the daily, so that whoever arrives late can still take part."""


def join_closes_at(starts_at: datetime) -> datetime:
    """The instant from which nobody may join the ceremony that starts at ``starts_at`` any more.

    The window to join goes from ``join_opens_at`` up to, and not including, this instant. It is a
    fixed time because the ceremony is not a record yet; once it is (AGI-62, HU-17), the window
    ends when the ceremony is closed.
    """
    return starts_at + JOIN_WINDOW_TAIL
