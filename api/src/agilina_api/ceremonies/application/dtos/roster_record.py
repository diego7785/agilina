from dataclasses import dataclass
from datetime import date

from agilina_api.ceremonies.application.dtos.roster_participant import RosterParticipant
from agilina_shared.enums import Language, OperationMode


@dataclass(frozen=True)
class RosterRecord:
    """What the ceremonies of a team's active sprint need from teams: how Agilina works in the
    team, the sprint's calendar and who takes part, in turn order."""

    language: Language
    mode: OperationMode
    start_date: date
    end_date: date
    time_zone: str
    """The IANA time zone the daily's time was captured in: it fixes the sprint's calendar
    (AD-31)."""
    participants: tuple[RosterParticipant, ...]
