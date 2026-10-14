from datetime import datetime, timedelta

JOIN_WINDOW_LEAD = timedelta(minutes=10)
"""How long before a ceremony starts the room opens to its participants."""


def join_opens_at(starts_at: datetime) -> datetime:
    """The instant from which a participant may join the ceremony that starts at ``starts_at``.

    The window to join goes from this instant to the start of the ceremony. Whoever arrives once
    the ceremony is under way is not covered yet: the ceremony as a record (when it started and
    ended) arrives with its own stories (AGI-62, HU-17).
    """
    return starts_at - JOIN_WINDOW_LEAD
