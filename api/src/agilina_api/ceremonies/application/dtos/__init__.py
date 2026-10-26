"""Data transfer objects of the ceremonies use cases: plain types, no framework."""

from agilina_api.ceremonies.application.dtos.ceremony_record import CeremonyRecord
from agilina_api.ceremonies.application.dtos.daily_participant import DailyParticipant
from agilina_api.ceremonies.application.dtos.participant_contact import ParticipantContact
from agilina_api.ceremonies.application.dtos.room_admission import RoomAdmission
from agilina_api.ceremonies.application.dtos.roster_participant import RosterParticipant
from agilina_api.ceremonies.application.dtos.roster_record import RosterRecord

__all__ = [
    "CeremonyRecord",
    "DailyParticipant",
    "ParticipantContact",
    "RoomAdmission",
    "RosterParticipant",
    "RosterRecord",
]
