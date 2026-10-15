from enum import StrEnum


class CeremonyEventType(StrEnum):
    """What can happen in a ceremony, as the worker reports it in the result.

    A closed list: a type the API does not know is a contract incompatibility, not a
    free-text note.
    """

    CEREMONY_STARTED = "ceremony_started"
    TURN_STARTED = "turn_started"
    TURN_ENDED = "turn_ended"
    DEGRADED = "degraded"
    CEREMONY_CLOSED = "ceremony_closed"
