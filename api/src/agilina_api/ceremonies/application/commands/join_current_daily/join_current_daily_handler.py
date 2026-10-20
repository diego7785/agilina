import logging
from collections.abc import Callable
from datetime import timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from agilina_api.ceremonies.application.commands.join_current_daily.join_current_daily import (
    JoinCurrentDaily,
)
from agilina_api.ceremonies.application.dtos import RoomAdmission
from agilina_api.ceremonies.application.errors import (
    DailyNotOpenError,
    NoActiveSprintError,
    NotADailyParticipantError,
)
from agilina_api.ceremonies.application.ports.outbound import (
    CeremoniesUnitOfWork,
    CeremonyRoster,
    Rooms,
)
from agilina_api.ceremonies.domain.ceremony import Ceremony
from agilina_api.shared.application.ports import Clock
from agilina_shared import room_name_for
from agilina_shared.sprint_calendar import daily_occurrences, join_opens_at, joinable_daily_at

logger = logging.getLogger(__name__)

ROOM_TOKEN_TTL = timedelta(hours=2)
"""How long the token of a room lets its bearer in (AGI-59)."""


class JoinCurrentDailyHandler:
    """It does not check who asks: the route lets only a member of the team get here. The rule
    of the participant does live here: only someone among the participants of the active
    sprint, as stored, gets a token, the team's admin included.

    Nothing is created for someone who may not join: the sprint, the participant and the window
    are checked before the ceremony is stored or the room opened. The ceremony of the occurrence
    is stored (or found) and committed before the room is opened, so if the room server fails
    the ceremony stays and a retry reuses it, with the same room. It returns the credential it
    issues, as a command that creates something returns its id.
    """

    def __init__(
        self,
        uow_factory: Callable[[], CeremoniesUnitOfWork],
        rosters: CeremonyRoster,
        rooms: Rooms,
        clock: Clock,
        room_server_url: str,
        new_id: Callable[[], UUID] = uuid4,
    ) -> None:
        self._uow_factory = uow_factory
        self._rosters = rosters
        self._rooms = rooms
        self._clock = clock
        self._room_server_url = room_server_url
        self._new_id = new_id

    async def handle(self, command: JoinCurrentDaily) -> RoomAdmission:
        roster = await self._rosters.active_roster_of(team_id=command.team_id)
        if roster is None:
            raise NoActiveSprintError(f"Team {command.team_id} has no active sprint")
        if command.user_id not in {member.user_id for member in roster.participants}:
            raise NotADailyParticipantError("The user is not a participant of the daily")
        now = self._clock.now()
        occurrences = daily_occurrences(
            start=roster.start_date,
            end=roster.end_date,
            local_time=roster.daily_time,
            time_zone=ZoneInfo(roster.time_zone),
        )
        # The dashboard's rule (AGI-60), so the button and the token never disagree.
        scheduled_at = joinable_daily_at(occurrences, now)
        if scheduled_at is None or now < join_opens_at(scheduled_at):
            raise DailyNotOpenError("No daily of the sprint is open to join now")
        async with self._uow_factory() as uow:
            ceremony = await uow.ceremonies.add_or_get(
                Ceremony.schedule(
                    ceremony_id=self._new_id(),
                    team_id=command.team_id,
                    sprint_id=roster.sprint_id,
                    scheduled_at=scheduled_at,
                )
            )
            await uow.commit()
        room_name = room_name_for(command.tenant, ceremony.id)
        await self._rooms.open(room_name)
        expires_at = now + ROOM_TOKEN_TTL
        token = self._rooms.admission_for(
            room_name=room_name, identity=str(command.user_id), expires_at=expires_at
        )
        logger.info(
            "Ceremony %s: user %s admitted to room %s until %s",
            ceremony.id,
            command.user_id,
            room_name,
            expires_at.isoformat(),
        )
        return RoomAdmission(
            room_name=room_name,
            token=token,
            expires_at=expires_at,
            livekit_url=self._room_server_url,
        )
