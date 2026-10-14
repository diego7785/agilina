"""The ``Sprint`` aggregate: it starts active, keeps its participants in turn order and can be
reconfigured whole; the daily takes at least one participant, each once and each an active
member, and a member who leaves the team leaves the daily with the turns closing up (HU-07)."""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from uuid import UUID

import pytest

from agilina_api.teams.domain.errors import (
    DailyParticipantNotAMemberError,
    DuplicateDailyParticipantError,
    NoDailyParticipantsError,
)
from agilina_api.teams.domain.sprint import DailyTime, Sprint, SprintPeriod, SprintStatus
from tests.api.builders import SprintBuilder, next_id

PERIOD = SprintPeriod(start=date(2026, 10, 5), end=date(2026, 10, 16))
DAILY = DailyTime(at=datetime(2026, 10, 5, 14, 0, tzinfo=UTC), time_zone="America/Bogota")


def _start(participants: Sequence[UUID], active_members: set[UUID]) -> Sprint:
    """The action under test: a sprint starts with these participants among these members."""
    return Sprint.start(
        sprint_id=next_id(),
        team_id=next_id(),
        number=1,
        period=PERIOD,
        daily_time=DAILY,
        participants=participants,
        active_members=active_members,
    )


def test_a_started_sprint_is_active_with_its_period_daily_time_and_team():
    sprint_id, team_id, ana = next_id(), next_id(), next_id()
    period = SprintPeriod(start=date(2026, 10, 5), end=date(2026, 10, 16))
    daily = DailyTime(at=datetime(2026, 10, 5, 14, 0, tzinfo=UTC), time_zone="America/Bogota")

    sprint = Sprint.start(
        sprint_id=sprint_id,
        team_id=team_id,
        number=12,
        period=period,
        daily_time=daily,
        participants=[ana],
        active_members={ana},
    )

    assert sprint.id == sprint_id and sprint.team_id == team_id and sprint.number == 12
    assert sprint.status is SprintStatus.ACTIVE
    assert sprint.period == period and sprint.daily_time == daily
    assert sprint.participants == (ana,)


def test_the_participants_keep_the_order_they_were_given_which_is_the_turn_order():
    ana, bruno, carla = next_id(), next_id(), next_id()

    sprint = SprintBuilder().with_participants(carla, ana, bruno).build()

    assert sprint.participants == (carla, ana, bruno)


def test_the_sprint_keeps_its_own_copy_of_the_participants():
    ana, bruno = next_id(), next_id()
    given = [ana, bruno]

    sprint = Sprint.start(
        sprint_id=next_id(),
        team_id=next_id(),
        number=1,
        period=SprintPeriod(start=date(2026, 10, 5), end=date(2026, 10, 16)),
        daily_time=DailyTime(
            at=datetime(2026, 10, 5, 14, 0, tzinfo=UTC), time_zone="America/Bogota"
        ),
        participants=given,
        active_members={ana, bruno},
    )
    given.reverse()

    assert sprint.participants == (ana, bruno)


def test_reconfiguring_replaces_the_period_the_daily_time_its_zone_and_the_order():
    ana, bruno, carla = next_id(), next_id(), next_id()
    sprint = SprintBuilder().with_participants(ana, bruno).build()
    period = SprintPeriod(start=date(2026, 10, 10), end=date(2026, 10, 24))
    tokyo = DailyTime(at=datetime(2026, 10, 9, 23, 0, tzinfo=UTC), time_zone="Asia/Tokyo")

    sprint.reconfigure(
        period=period,
        daily_time=tokyo,
        participants=[bruno, carla, ana],
        active_members={ana, bruno, carla},
    )

    assert sprint.period == period
    assert sprint.daily_time == tokyo and sprint.daily_time.time_zone == "Asia/Tokyo"
    assert sprint.participants == (bruno, carla, ana)


def test_reconfiguring_does_not_change_the_status():
    ana = next_id()
    active = SprintBuilder().build()
    closed = SprintBuilder().closed().build()
    period = SprintPeriod(start=date(2026, 10, 12), end=date(2026, 10, 23))

    for sprint in (active, closed):
        sprint.reconfigure(
            period=period, daily_time=sprint.daily_time, participants=(ana,), active_members={ana}
        )

    assert active.status is SprintStatus.ACTIVE and closed.status is SprintStatus.CLOSED


def test_a_stored_sprint_is_restored_with_the_status_it_was_saved_with():
    planned = SprintBuilder().planned().build()

    assert planned.status is SprintStatus.PLANNED


# ------------------------------------------------------------ participant rules --
def test_only_the_members_chosen_take_part_in_the_daily_not_every_member():
    ana, bruno, carla = next_id(), next_id(), next_id()

    sprint = _start([bruno], {ana, bruno, carla})

    assert sprint.participants == (bruno,)


def test_a_daily_without_participants_is_refused():
    with pytest.raises(NoDailyParticipantsError):
        _start([], {next_id()})


def test_the_same_person_cannot_take_two_turns():
    ana, bruno = next_id(), next_id()

    with pytest.raises(DuplicateDailyParticipantError):
        _start([ana, bruno, ana], {ana, bruno})


def test_someone_who_is_not_an_active_member_cannot_take_part():
    """``active_members`` holds only the active ones: an outsider and a removed member are
    both left out of it."""
    ana, outsider = next_id(), next_id()

    with pytest.raises(DailyParticipantNotAMemberError):
        _start([ana, outsider], {ana})


def test_a_reconfiguration_that_breaks_a_participant_rule_changes_nothing():
    ana, bruno, outsider = next_id(), next_id(), next_id()
    sprint = SprintBuilder().with_participants(ana, bruno).build()
    before = (sprint.period, sprint.daily_time, sprint.participants)
    refusals = [
        ((), NoDailyParticipantsError),
        ((bruno, bruno), DuplicateDailyParticipantError),
        ((bruno, outsider), DailyParticipantNotAMemberError),
    ]

    for participants, error in refusals:
        with pytest.raises(error):
            sprint.reconfigure(
                period=SprintPeriod(start=date(2026, 10, 12), end=date(2026, 10, 23)),
                daily_time=DailyTime(
                    at=datetime(2026, 10, 11, 23, 0, tzinfo=UTC), time_zone="Asia/Tokyo"
                ),
                participants=participants,
                active_members={ana, bruno},
            )

        assert (sprint.period, sprint.daily_time, sprint.participants) == before


def test_a_member_who_left_cannot_be_kept_in_the_daily_when_it_is_reconfigured():
    ana, bruno = next_id(), next_id()
    sprint = SprintBuilder().with_participants(ana, bruno).build()

    with pytest.raises(DailyParticipantNotAMemberError):
        sprint.reconfigure(
            period=sprint.period,
            daily_time=sprint.daily_time,
            participants=(ana, bruno),
            active_members={ana},
        )

    assert sprint.participants == (ana, bruno)


# ------------------------------------------------------- withdraw a participant --
def test_withdrawing_a_participant_closes_up_the_turns():
    ana, bruno, carla = next_id(), next_id(), next_id()
    sprint = SprintBuilder().with_participants(ana, bruno, carla).build()

    sprint.withdraw_participant(bruno)

    # Carla moves from turn 3 to turn 2: the order still goes from 1 with no gaps.
    assert sprint.participants == (ana, carla)
    assert {user: turn for turn, user in enumerate(sprint.participants, 1)} == {ana: 1, carla: 2}


def test_withdrawing_the_first_participant_moves_everyone_one_turn_forward():
    ana, bruno, carla = next_id(), next_id(), next_id()
    sprint = SprintBuilder().with_participants(ana, bruno, carla).build()

    sprint.withdraw_participant(ana)

    assert sprint.participants == (bruno, carla)


def test_withdrawing_someone_who_is_not_a_participant_changes_nothing():
    ana, bruno = next_id(), next_id()
    sprint = SprintBuilder().with_participants(ana, bruno).build()

    sprint.withdraw_participant(next_id())

    assert sprint.participants == (ana, bruno)


def test_withdrawing_the_only_participant_leaves_the_daily_with_none():
    """The rule of at least one participant holds when the sprint is configured; a member's
    removal is not blocked by the daily (Q4)."""
    ana = next_id()
    sprint = SprintBuilder().with_participants(ana).build()

    sprint.withdraw_participant(ana)

    assert sprint.participants == ()
    assert sprint.status is SprintStatus.ACTIVE


def test_withdrawing_does_not_touch_the_period_or_the_daily_time():
    ana, bruno = next_id(), next_id()
    sprint = SprintBuilder().with_participants(ana, bruno).build()
    before = (sprint.id, sprint.team_id, sprint.period, sprint.daily_time, sprint.status)

    sprint.withdraw_participant(ana)

    assert (sprint.id, sprint.team_id, sprint.period, sprint.daily_time, sprint.status) == before


@pytest.mark.parametrize("number", [0, -1])
def test_a_sprint_number_below_one_is_a_programming_error(number):
    with pytest.raises(ValueError, match="starts at 1"):
        Sprint.start(
            sprint_id=next_id(),
            team_id=next_id(),
            number=number,
            period=PERIOD,
            daily_time=DAILY,
            participants=[],
            active_members=set(),
        )


def test_a_restored_sprint_keeps_the_number_it_was_stored_with():
    assert SprintBuilder().numbered(7).build().number == 7


def test_reconfiguring_the_sprint_does_not_change_its_number():
    ana = next_id()
    sprint = SprintBuilder().numbered(3).with_participants(ana).build()

    sprint.reconfigure(
        period=SprintPeriod(start=date(2026, 11, 2), end=date(2026, 11, 13)),
        daily_time=DAILY,
        participants=[ana],
        active_members={ana},
    )

    assert sprint.number == 3
