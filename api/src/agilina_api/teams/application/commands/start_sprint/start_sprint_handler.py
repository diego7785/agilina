import logging
from collections.abc import Callable
from uuid import UUID, uuid4

from agilina_api.teams.application.commands.start_sprint.start_sprint import StartSprint
from agilina_api.teams.application.ports.outbound import TeamsUnitOfWork
from agilina_api.teams.domain.errors import ActiveSprintExistsError, TeamNotFoundError
from agilina_api.teams.domain.sprint import DailyTime, Sprint, SprintPeriod

logger = logging.getLogger(__name__)


class StartSprintHandler:
    """It does not check who asks: the route lets only the team's admins get here.

    The team is loaded first, which locks its row until the transaction ends (the same lock
    every change to its members takes), so starting a sprint and removing a member never
    interleave, and the participants are checked against the team's active members inside
    that transaction. A team has at most one active sprint: the use case asks
    ``ActiveSprints`` once the team is locked and refuses with ``ActiveSprintExistsError``;
    the ``sprint_one_active_per_team`` index backs it, and the repository answers the same
    error if it is ever reached. The sprint takes the next number of its team
    (``next_number``, under the same lock) and is stored ``active`` in one transaction with its
    participants. It returns only the new sprint's id (CQRS).

    Once committed, the start is logged with who asked.
    """

    def __init__(
        self,
        uow_factory: Callable[[], TeamsUnitOfWork],
        new_id: Callable[[], UUID] = uuid4,
    ) -> None:
        self._uow_factory = uow_factory
        self._new_id = new_id

    async def handle(self, command: StartSprint) -> UUID:
        async with self._uow_factory() as uow:
            team = await uow.teams.get(command.team_id)
            if team is None:
                raise TeamNotFoundError(f"Team {command.team_id} does not exist")
            if await uow.active_sprints.has_active_sprint(team.id):
                raise ActiveSprintExistsError(f"Team {team.id} already has an active sprint")
            sprint = Sprint.start(
                sprint_id=self._new_id(),
                team_id=team.id,
                number=await uow.sprints.next_number(team.id),
                period=SprintPeriod(start=command.start_date, end=command.end_date),
                daily_time=DailyTime(at=command.daily_time, time_zone=command.time_zone),
                participants=command.participants,
                active_members=team.active_member_ids,
            )
            await uow.sprints.add(sprint)
            await uow.commit()
        logger.info("Team %s: user %s started sprint %s", team.id, command.requested_by, sprint.id)
        return sprint.id
