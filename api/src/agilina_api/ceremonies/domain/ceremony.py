from collections.abc import Collection, Mapping
from datetime import datetime
from uuid import UUID

from agilina_api.ceremonies.domain.errors import NotAParticipantError, ResultAlreadyReceivedError
from agilina_api.shared_kernel import AggregateRoot


class Ceremony(AggregateRoot[UUID]):
    """A ceremony of a team's sprint and the result the agent worker delivered for it, if any.

    The result is known by its digest (the SHA-256 of the canonical delivery): the rules only
    need to tell the same delivery from another one. The constructor restores a stored ceremony
    as it is.
    """

    def __init__(
        self,
        *,
        ceremony_id: UUID,
        team_id: UUID,
        sprint_id: UUID,
        scheduled_at: datetime,
        result_digest: str | None,
    ) -> None:
        super().__init__(ceremony_id)
        self._team_id = team_id
        self._sprint_id = sprint_id
        self._scheduled_at = scheduled_at
        self._result_digest = result_digest

    @classmethod
    def schedule(
        cls, *, ceremony_id: UUID, team_id: UUID, sprint_id: UUID, scheduled_at: datetime
    ) -> "Ceremony":
        """A new ceremony for one occurrence of the sprint's daily, with no result yet (AGI-59).

        Each occurrence has its own ceremony, and with it its own room: the repository keeps it
        to one per team, sprint and instant (``CeremonyRepository.add_or_get``).
        """
        return cls(
            ceremony_id=ceremony_id,
            team_id=team_id,
            sprint_id=sprint_id,
            scheduled_at=scheduled_at,
            result_digest=None,
        )

    @property
    def team_id(self) -> UUID:
        return self._team_id

    @property
    def sprint_id(self) -> UUID:
        return self._sprint_id

    @property
    def scheduled_at(self) -> datetime:
        return self._scheduled_at

    @property
    def result_digest(self) -> str | None:
        return self._result_digest

    def receive_result(
        self, digest: str, speakers: Mapping[str, UUID], participants: Collection[UUID]
    ) -> bool:
        """Take the delivery whose digest is ``digest``; ``True`` when it is new and must be
        stored, ``False`` when it is the one already received (nothing to store).

        ``speakers`` maps where each attribution is in the delivery (``segments.0.user_id``) to
        the user it names; every one must be in ``participants``. The same delivery again is
        accepted before anything else is checked: a retry of the worker must not fail because
        someone left the sprint's participants since.
        """
        if self._result_digest == digest:
            return False
        if self._result_digest is not None:
            raise ResultAlreadyReceivedError(f"Ceremony {self.id} already has another result")
        strangers = tuple(
            field for field, user_id in speakers.items() if user_id not in participants
        )
        if strangers:
            raise NotAParticipantError(strangers)
        self._result_digest = digest
        return True
