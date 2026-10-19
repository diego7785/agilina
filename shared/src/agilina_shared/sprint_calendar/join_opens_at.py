from datetime import datetime, timedelta

JOIN_WINDOW_LEAD = timedelta(minutes=10)
"""How long before a ceremony starts the room opens to its participants."""


def join_opens_at(starts_at: datetime) -> datetime:
    """The instant from which a participant may join the ceremony that starts at ``starts_at``.

    The window to join goes from this instant up to ``join_closes_at``, a while after the start,
    so that whoever arrives late can still join (AGI-60).
    """
    return starts_at - JOIN_WINDOW_LEAD
