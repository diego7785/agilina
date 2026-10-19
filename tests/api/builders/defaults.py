"""The values every builder starts from."""

from datetime import UTC, date, datetime, time

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
"""The instant the fake clock starts at and the default moment things are created."""

TOKEN = "T" * 43
"""A well-formed activation token (43 characters, like ``token_urlsafe(32)``)."""

PASSWORD = "a-long-enough-password"  # noqa: S105 - a test value

EMAIL = "julian@example.test"
FULL_NAME = "Julián Torres"
TEAM_NAME = "Atlas"

SPRINT_START = date(2026, 10, 5)
"""A Monday, the day after ``NOW``: a sprint that starts there has not started at ``NOW``."""
SPRINT_END = date(2026, 10, 16)
"""A Friday: with ``SPRINT_START`` the period has 12 calendar days, weekends included."""
DAILY_TIME_ZONE = "America/Bogota"
DAILY_TIME = datetime(2026, 10, 5, 14, 0, tzinfo=UTC)
"""The daily's anchor: 09:00 in ``DAILY_TIME_ZONE`` (UTC-5, no daylight saving)."""
DAILY_LOCAL_TIME = time(9, 0)
"""``DAILY_TIME`` as the wall-clock time it repeats every day in ``DAILY_TIME_ZONE``."""
