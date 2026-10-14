from collections.abc import Collection, Sequence
from uuid import UUID

from agilina_api.shared_kernel import AggregateRoot
from agilina_api.teams.domain.errors import (
    DailyParticipantNotAMemberError,
    DuplicateDailyParticipantError,
    NoDailyParticipantsError,
)
from agilina_api.teams.domain.sprint.daily_time import DailyTime
from agilina_api.teams.domain.sprint.sprint_period import SprintPeriod
from agilina_api.teams.domain.sprint.sprint_status import SprintStatus


def _daily_participants(
    participants: Sequence[UUID], active_members: Collection[UUID]
) -> tuple[UUID, ...]:
    """The daily's participants as configured: at least one, each once, and each an active
    member of the team."""
    if not participants:
        raise NoDailyParticipantsError("The daily needs at least one participant")
    if len(set(participants)) != len(participants):
        raise DuplicateDailyParticipantError("A daily participant appears more than once")
    for user_id in participants:
        if user_id not in active_members:
            raise DailyParticipantNotAMemberError(
                f"User {user_id} is not an active member of the team"
            )
    return tuple(participants)


class Sprint(AggregateRoot[UUID]):
    """A team's sprint: its period, the daily's time and who is called to the daily, in turn
    order (HU-07).

    ``participants`` holds the ``app_user`` ids of the daily's participants; the position in
    the tuple is the turn order, so the order goes from 1 to k with no gaps by construction.
    The sprint is not part of the ``Team`` aggregate: the use cases load (and lock) the team
    first and hand the sprint what it needs from it, its active members.

    Configuring it (``start``, ``reconfigure``) asks for at least one participant, none twice
    and all of them active members. Removing a member afterwards (``withdraw_participant``) may
    leave it with none: the member's removal is not blocked by the daily.

    The constructor restores a stored sprint as it is, with no rule checked again. Its ``number`` is
    assigned by ``start`` and never changes (``reconfigure`` does not touch it).
    """

    def __init__(  # noqa: PLR0913
        self,
        *,
        sprint_id: UUID,
        team_id: UUID,
        number: int,
        period: SprintPeriod,
        daily_time: DailyTime,
        participants: Sequence[UUID],
        status: SprintStatus,
    ) -> None:
        super().__init__(sprint_id)
        self._team_id = team_id
        self._number = number
        self._period = period
        self._daily_time = daily_time
        self._participants = tuple(participants)
        self._status = status

    @classmethod
    def start(
        cls,
        *,
        sprint_id: UUID,
        team_id: UUID,
        number: int,
        period: SprintPeriod,
        daily_time: DailyTime,
        participants: Sequence[UUID],
        active_members: Collection[UUID],
    ) -> "Sprint":
        """A new sprint of the team, already ``active``: saving the sprint starts it (HU-07);
        closing it belongs to HU-10. ``active_members`` are the ``app_user`` ids of the
        team's active members, the only ones who may take part in the daily.

        Whether the team already has an active sprint is not the sprint's to know: the use
        case asks it, and the database backs it with ``sprint_one_active_per_team``.

        ``number`` is the sprint's number in its team, which the use case takes from
        ``SprintRepository.next_number``; it is never typed by a person, so a number below 1 is
        a programming error (``ValueError``) and not a business rule.
        """
        if number < 1:
            raise ValueError("A sprint number starts at 1")
        return cls(
            sprint_id=sprint_id,
            team_id=team_id,
            number=number,
            period=period,
            daily_time=daily_time,
            participants=_daily_participants(participants, active_members),
            status=SprintStatus.ACTIVE,
        )

    # ------------------------------------------------------------ read state --
    @property
    def team_id(self) -> UUID:
        return self._team_id

    @property
    def number(self) -> int:
        """The sprint's number in its team (the 12 of "Sprint 12"): fixed when it starts, never
        edited."""
        return self._number

    @property
    def period(self) -> SprintPeriod:
        return self._period

    @property
    def daily_time(self) -> DailyTime:
        return self._daily_time

    @property
    def participants(self) -> tuple[UUID, ...]:
        """The daily's participants, in turn order."""
        return self._participants

    @property
    def status(self) -> SprintStatus:
        return self._status

    # -------------------------------------------------------------- behavior --
    def reconfigure(
        self,
        *,
        period: SprintPeriod,
        daily_time: DailyTime,
        participants: Sequence[UUID],
        active_members: Collection[UUID],
    ) -> None:
        """Replace the period, the daily's time (with its capture time zone) and the
        participants with their order, with the same rules as ``start``. The status does not
        change, and nothing changes when a rule is broken."""
        self._participants = _daily_participants(participants, active_members)
        self._period = period
        self._daily_time = daily_time

    def withdraw_participant(self, user_id: UUID) -> None:
        """Take a member who left the team out of the daily (HU-07).

        The turn order closes up: whoever came after them moves one turn forward, so the
        order stays from 1 with no gaps. Someone who was not a participant changes nothing,
        and the last participant may leave too: the sprint keeps no participant until it is
        configured again.
        """
        self._participants = tuple(
            participant for participant in self._participants if participant != user_id
        )
