"""The facilitation machine is tested without a room, audio or network: it is
the engine of the ceremony and must be verifiable in seconds."""

from uuid import uuid4

import pytest

from agilina_agent.domain.facilitation import (
    ActionNotAllowedError,
    FacilitationMachine,
    FacilitationState,
)
from agilina_shared.contract import CeremonyContext, ParticipantContext
from agilina_shared.enums import Language, OperationMode, TeamRole

ADMIN = "sm-1"
MEMBER_A = "dev-1"
MEMBER_B = "dev-2"


def _context(language: Language = Language.ES) -> CeremonyContext:
    return CeremonyContext(
        tenant="acme",
        ceremony_id=uuid4(),
        team_id=uuid4(),
        sprint_id=uuid4(),
        room="ceremony-1",
        language=language,
        mode=OperationMode.SUPPORT,
        sprint_day=4,
        sprint_total_days=15,
        participants=[
            ParticipantContext(
                user_id=uuid4(),
                name="Diego",
                room_identity=ADMIN,
                role=TeamRole.ADMIN,
                turn_order=1,
            ),
            ParticipantContext(
                user_id=uuid4(),
                name="Angélica",
                room_identity=MEMBER_A,
                role=TeamRole.MEMBER,
                turn_order=2,
            ),
            ParticipantContext(
                user_id=uuid4(),
                name="Oscar",
                room_identity=MEMBER_B,
                role=TeamRole.MEMBER,
                turn_order=3,
            ),
        ],
    )


def _started_machine_with_two_turns_handed_over() -> FacilitationMachine:
    machine = FacilitationMachine(context=_context())
    machine.start(ADMIN)
    machine.hand_over_turn()
    machine.hand_over_turn()
    return machine


def test_agilina_starts_waiting_without_streaming_audio():
    machine = FacilitationMachine(context=_context())
    assert machine.state is FacilitationState.WAITING
    assert machine.current_turn is None


def test_the_greeting_announces_the_sprint_day():
    machine = FacilitationMachine(context=_context())
    greeting = machine.start(ADMIN)
    assert "4" in greeting and "15" in greeting


def test_a_member_cannot_start_the_ceremony():
    machine = FacilitationMachine(context=_context())
    with pytest.raises(ActionNotAllowedError):
        machine.start(MEMBER_A)


def test_someone_outside_the_roster_controls_nothing():
    machine = FacilitationMachine(context=_context())
    with pytest.raises(ActionNotAllowedError):
        machine.start("intruder")


def test_turns_follow_the_configured_order():
    machine = FacilitationMachine(context=_context())
    machine.start(ADMIN)

    machine.hand_over_turn()
    assert machine.current_turn.name == "Diego"
    machine.hand_over_turn()
    assert machine.current_turn.name == "Angélica"
    machine.hand_over_turn()
    assert machine.current_turn.name == "Oscar"
    assert machine.hand_over_turn() is None


def test_everyone_ends_their_own_turn():
    machine = _started_machine_with_two_turns_handed_over()

    assert machine.current_turn.room_identity == MEMBER_A
    machine.end_turn(MEMBER_A)
    assert machine.current_turn.room_identity == MEMBER_B


def test_a_member_cannot_end_someone_elses_turn():
    machine = _started_machine_with_two_turns_handed_over()

    with pytest.raises(ActionNotAllowedError):
        machine.end_turn(MEMBER_B)


def test_the_admin_can_end_anyones_turn():
    machine = _started_machine_with_two_turns_handed_over()

    machine.end_turn(ADMIN)
    assert machine.current_turn.room_identity == MEMBER_B


def test_only_the_admin_closes_the_ceremony():
    machine = FacilitationMachine(context=_context())
    machine.start(ADMIN)

    with pytest.raises(ActionNotAllowedError):
        machine.close(MEMBER_A)

    machine.close(ADMIN)
    assert machine.state is FacilitationState.CLOSED


def test_without_transcription_the_ceremony_goes_on_in_degraded_mode():
    machine = FacilitationMachine(context=_context())
    machine.start(ADMIN)

    announcement = machine.degrade("The transcription service is not responding")

    assert machine.state is FacilitationState.DEGRADED
    assert announcement
    assert machine.degradation_reason


def test_the_ceremony_is_conducted_the_same_way_in_english():
    """Language is a team attribute and parameterizes everything Agilina says."""
    machine = FacilitationMachine(context=_context(Language.EN))

    greeting = machine.start(ADMIN)
    hand_over = machine.hand_over_turn()

    assert "sprint" in greeting.lower()
    assert "turn" in hand_over.lower()
    assert "Diego" in hand_over
