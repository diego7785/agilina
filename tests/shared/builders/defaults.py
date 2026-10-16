"""The values every contract builder starts from."""

from datetime import UTC, datetime

TENANT = "acme"
"""One of the two development tenants."""

STARTED_AT = datetime(2026, 10, 5, 14, 0, tzinfo=UTC)
"""The daily of the first sprint day: 09:00 in America/Bogota."""
CLOSED_AT = datetime(2026, 10, 5, 14, 15, tzinfo=UTC)
