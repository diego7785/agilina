class RoomServiceUnavailableError(Exception):
    """The room server did not answer, failed or is not configured. Not a business rule: it
    is an outage, and the interface reports it as such."""
