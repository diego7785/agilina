from uuid import UUID

from agilina_api.ceremonies.application.dtos import RosterParticipant, RosterRecord
from agilina_api.ceremonies.application.ports.outbound import CeremonyRoster
from agilina_api.teams.application.ports.outbound import SprintQueries, TeamQueries


class TeamsBackedCeremonyRoster(CeremonyRoster):
    """The roster of a ceremony, for ceremonies, from teams' own reads: the team's language
    and mode, its active sprint with its participants in turn order, and their stored roles."""

    def __init__(self, team_queries: TeamQueries, sprint_queries: SprintQueries) -> None:
        self._team_queries = team_queries
        self._sprint_queries = sprint_queries

    async def roster_of(self, *, team_id: UUID, sprint_id: UUID) -> RosterRecord | None:
        sprint = await self._sprint_queries.active_sprint_of(team_id)
        if sprint is None or sprint.sprint_id != sprint_id:
            return None
        team = await self._team_queries.get_team(team_id)
        if team is None:
            return None
        roles = {
            member.user_id: member.role
            for member in (await self._team_queries.list_members(team_id)).members
        }
        # A participant removed between the two reads is left out, and the turns stay 1..N.
        in_turn_order = [user_id for user_id in sprint.participants if user_id in roles]
        return RosterRecord(
            language=team.language,
            mode=team.mode,
            start_date=sprint.start_date,
            end_date=sprint.end_date,
            time_zone=sprint.time_zone,
            participants=tuple(
                RosterParticipant(user_id=user_id, role=roles[user_id], turn_order=turn)
                for turn, user_id in enumerate(in_turn_order, start=1)
            ),
        )
