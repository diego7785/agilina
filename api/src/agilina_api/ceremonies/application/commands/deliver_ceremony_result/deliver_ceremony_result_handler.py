import hashlib
import logging
from collections.abc import Callable
from uuid import UUID
from zoneinfo import ZoneInfo

from agilina_api.ceremonies.application.commands.deliver_ceremony_result.deliver_ceremony_result import (  # noqa: E501
    DeliverCeremonyResult,
)
from agilina_api.ceremonies.application.errors import (
    CeremonyNotFoundError,
    ResultOfAnotherCeremonyError,
)
from agilina_api.ceremonies.application.ports.outbound import (
    CeremoniesUnitOfWork,
    CeremonyRoster,
)
from agilina_api.shared.application.ports import Clock
from agilina_shared import CeremonyResult
from agilina_shared.sprint_calendar import SprintPhase, sprint_day_at

logger = logging.getLogger(__name__)


class DeliverCeremonyResultHandler:
    """It does not check who asks: the route lets only the agent worker get here.

    The ceremony is loaded first, which locks its row until the transaction ends, so two
    deliveries of the same ceremony never interleave: the second waits and finds the first one's
    digest. A delivery is known by the SHA-256 of its canonical JSON (the contract's own
    serialization), so the worker's retry of the same file is accepted again without storing
    anything and another result is refused (``Ceremony.receive_result``). Who may speak is the
    roster of the ceremony's sprint, and a ceremony the worker could not get the context of
    (gone, of a sprint no longer active, or scheduled before its sprint starts) is not found
    either. The result, its segments and its events are stored in one transaction.

    It neither starts the post-processing (AGI-26) nor closes the room (AGI-63).
    """

    def __init__(
        self,
        uow_factory: Callable[[], CeremoniesUnitOfWork],
        rosters: CeremonyRoster,
        clock: Clock,
    ) -> None:
        self._uow_factory = uow_factory
        self._rosters = rosters
        self._clock = clock

    async def handle(self, command: DeliverCeremonyResult) -> None:
        result = command.result
        if result.ceremony_id != command.ceremony_id:
            raise ResultOfAnotherCeremonyError(
                f"The result of ceremony {result.ceremony_id} was delivered to "
                f"{command.ceremony_id}"
            )
        digest = hashlib.sha256(result.model_dump_json().encode()).hexdigest()
        async with self._uow_factory() as uow:
            ceremony = await uow.ceremonies.lock(command.ceremony_id)
            if ceremony is None:
                raise CeremonyNotFoundError("The ceremony does not exist")
            # A retry whose first 202 was lost is accepted even if the sprint closed since.
            if ceremony.result_digest == digest:
                logger.info("Ceremony %s: the same result arrived again", ceremony.id)
                return
            roster = await self._rosters.roster_of(
                team_id=ceremony.team_id, sprint_id=ceremony.sprint_id
            )
            if roster is None:
                raise CeremonyNotFoundError("The ceremony's sprint is not the team's active one")
            day = sprint_day_at(
                start=roster.start_date,
                end=roster.end_date,
                time_zone=ZoneInfo(roster.time_zone),
                now=ceremony.scheduled_at,
            )
            if day.phase is SprintPhase.NOT_STARTED:
                raise CeremonyNotFoundError("The ceremony is scheduled before its sprint starts")
            participants = {member.user_id for member in roster.participants}
            # The same delivery already returned above, so this one is new.
            ceremony.receive_result(digest, _speakers(result), participants)
            await uow.ceremonies.add_result(ceremony, result, received_at=self._clock.now())
            await uow.commit()
        logger.info(
            "Ceremony %s: result received (%d segments, %d events)",
            ceremony.id,
            len(result.segments),
            len(result.events),
        )


def _speakers(result: CeremonyResult) -> dict[str, UUID]:
    """Where each attribution of the result is, mapped to the user it names."""
    speakers = {
        f"segments.{index}.user_id": segment.user_id
        for index, segment in enumerate(result.segments)
    }
    for index, event in enumerate(result.events):
        if event.user_id is not None:
            speakers[f"events.{index}.user_id"] = event.user_id
    return speakers
