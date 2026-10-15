from zoneinfo import ZoneInfo

from agilina_api.ceremonies.application.errors import CeremonyNotFoundError
from agilina_api.ceremonies.application.ports.outbound import (
    CeremonyQueries,
    CeremonyRoster,
    ParticipantNames,
)
from agilina_api.ceremonies.application.queries.get_ceremony_context.get_ceremony_context import (
    GetCeremonyContext,
)
from agilina_shared import CeremonyContext, ParticipantContext, room_name_for
from agilina_shared.sprint_calendar import SprintPhase, sprint_day_at


class GetCeremonyContextHandler:
    """It does not check who asks: the route lets only the agent worker get here.

    It answers the shared ``CeremonyContext`` as it is: the contract is the DTO, so it is not
    copied into another model. The day N of M is the one of the instant the ceremony is
    scheduled, in the sprint's calendar (AD-31), not the one of the moment the worker asks.
    A ceremony of a sprint that is no longer the team's active one is not found: its
    participants and its calendar are gone.
    """

    def __init__(
        self, ceremonies: CeremonyQueries, rosters: CeremonyRoster, names: ParticipantNames
    ) -> None:
        self._ceremonies = ceremonies
        self._rosters = rosters
        self._names = names

    async def handle(self, query: GetCeremonyContext) -> CeremonyContext:
        ceremony = await self._ceremonies.ceremony_of(query.ceremony_id)
        if ceremony is None:
            raise CeremonyNotFoundError("The ceremony does not exist")
        roster = await self._rosters.roster_of(
            team_id=ceremony.team_id, sprint_id=ceremony.sprint_id
        )
        if roster is None:
            raise CeremonyNotFoundError("The ceremony's sprint is not the team's active one")
        names = await self._names.names_of([member.user_id for member in roster.participants])
        day = sprint_day_at(
            start=roster.start_date,
            end=roster.end_date,
            time_zone=ZoneInfo(roster.time_zone),
            now=ceremony.scheduled_at,
        )
        if day.phase is SprintPhase.NOT_STARTED:
            raise CeremonyNotFoundError("The ceremony is scheduled before its sprint starts")
        return CeremonyContext(
            tenant=query.tenant,
            ceremony_id=query.ceremony_id,
            team_id=ceremony.team_id,
            sprint_id=ceremony.sprint_id,
            room=room_name_for(query.tenant, query.ceremony_id),
            language=roster.language,
            mode=roster.mode,
            sprint_day=day.number,
            sprint_total_days=day.total,
            participants=[
                ParticipantContext(
                    user_id=member.user_id,
                    name=names[member.user_id],
                    room_identity=str(member.user_id),
                    role=member.role,
                    turn_order=member.turn_order,
                )
                for member in roster.participants
            ],
        )
