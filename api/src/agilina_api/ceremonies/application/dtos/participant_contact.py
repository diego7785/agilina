from dataclasses import dataclass


@dataclass(frozen=True)
class ParticipantContact:
    """How a participant of a ceremony is called and reached, as identity holds it."""

    full_name: str
    email: str
