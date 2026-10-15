"""Injectable clock so that runs and tests control time."""

from datetime import UTC, datetime
from typing import Protocol

ISO_UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class Clock(Protocol):
    """Source of the current instant."""

    def now(self) -> datetime:
        """Return the current instant, always timezone-aware in UTC."""


class SystemClock:
    """Clock backed by the system time."""

    def now(self) -> datetime:
        """Return the current instant in UTC."""
        return datetime.now(UTC)


def format_utc(moment: datetime) -> str:
    """Format an instant as ISO 8601 in UTC with the ``Z`` suffix (seconds precision)."""
    return moment.astimezone(UTC).strftime(ISO_UTC_FORMAT)
