from agilina_api.ceremonies.application.dtos import DailyParticipant
from agilina_api.ceremonies.application.errors import (
    NoActiveSprintError,
    NotADailyParticipantError,
)
from agilina_api.ceremonies.application.ports.outbound import (
    CeremonyRoster,
    ParticipantContacts,
)
from agilina_api.ceremonies.application.queries.get_current_daily_participants.get_current_daily_participants import (  # noqa: E501
    GetCurrentDailyParticipants,
)


class GetCurrentDailyParticipantsHandler:
    """It does not check who asks: the route lets only a member of the team get here. The rule
    of the participant does live here, the same as joining the room's: only someone among the
    participants of the active sprint, as stored, sees the others' names and emails, the team's
    admin included. It does not ask for the daily's window: the room shows its list while it is
    open, and the list is the same before and after.

    A participant whose account is gone is left out rather than failing the whole list.
    """

    def __init__(self, rosters: CeremonyRoster, contacts: ParticipantContacts) -> None:
        self._rosters = rosters
        self._contacts = contacts

    async def handle(self, query: GetCurrentDailyParticipants) -> tuple[DailyParticipant, ...]:
        roster = await self._rosters.active_roster_of(team_id=query.team_id)
        if roster is None:
            raise NoActiveSprintError(f"Team {query.team_id} has no active sprint")
        user_ids = [member.user_id for member in roster.participants]
        if query.user_id not in user_ids:
            raise NotADailyParticipantError("The user is not a participant of the daily")
        contacts = await self._contacts.contacts_of(user_ids)
        return tuple(
            DailyParticipant(
                room_identity=str(user_id),
                full_name=contacts[user_id].full_name,
                email=contacts[user_id].email,
            )
            for user_id in user_ids
            if user_id in contacts
        )
