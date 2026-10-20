"""Data transfer objects of the ceremonies use cases: plain types, no framework."""

from agilina_api.ceremonies.application.dtos.ceremony_record import CeremonyRecord
from agilina_api.ceremonies.application.dtos.room_admission import RoomAdmission
from agilina_api.ceremonies.application.dtos.roster_participant import RosterParticipant
from agilina_api.ceremonies.application.dtos.roster_record import RosterRecord

__all__ = [
    "CeremonyRecord",
    "RoomAdmission",
    "RosterParticipant",
    "RosterRecord",
]
