"""The contract is what keeps the worker and the API aligned: if these tests
fail, one deployable stopped understanding the other."""

import pytest
from pydantic import ValidationError

from agilina_shared import (
    CeremonyContext,
    CeremonyEvent,
    CeremonyEventType,
    CeremonyResult,
    CeremonyStatus,
    Language,
    OperationMode,
    ResultReceipt,
    TeamRole,
)
from tests.shared.builders import (
    CLOSED_AT,
    STARTED_AT,
    CeremonyContextBuilder,
    CeremonyEventBuilder,
    CeremonyResultBuilder,
    ParticipantContextBuilder,
    TranscriptSegmentBuilder,
    next_id,
)


def test_context_survives_a_json_round_trip():
    context = CeremonyContextBuilder().build()

    restored = CeremonyContext.model_validate_json(context.model_dump_json())

    assert restored == context


def test_one_context_carries_everything_the_worker_needs_to_facilitate():
    """CA1 and CA7: sprint, day, participants, order, language, mode and tenant, in one go."""
    diego = ParticipantContextBuilder().named("Diego").as_admin().in_turn(1).build()
    angelica = ParticipantContextBuilder().named("Angélica").in_turn(2).build()
    context = (
        CeremonyContextBuilder()
        .for_tenant("ecomoda")
        .in_language(Language.EN)
        .with_participants(diego, angelica)
        .build()
    )

    data = context.model_dump(mode="json")

    assert data["tenant"] == "ecomoda"
    assert data["sprint_id"] == str(context.sprint_id)
    assert (data["sprint_day"], data["sprint_total_days"]) == (3, 15)
    assert data["language"] == "en"
    assert data["mode"] == "support"
    assert [(p["name"], p["role"], p["turn_order"]) for p in data["participants"]] == [
        ("Diego", "admin", 1),
        ("Angélica", "member", 2),
    ]


def test_the_room_identity_of_a_participant_is_their_user_id():
    participant = ParticipantContextBuilder().build()

    assert participant.room_identity == str(participant.user_id)


def test_thresholds_have_the_agreed_starting_values():
    context = CeremonyContextBuilder().build()

    assert context.silence_seconds == 10
    assert context.stuck_turn_seconds == 30


def test_an_unknown_field_breaks_immediately():
    """An incompatibility between versions must fail, not go unnoticed."""
    data = CeremonyContextBuilder().build().model_dump(mode="json")
    data["field_that_does_not_exist"] = True

    with pytest.raises(ValidationError):
        CeremonyContext.model_validate(data)


@pytest.mark.parametrize("field", ["tenant", "sprint_id"])
def test_a_context_without_tenant_or_sprint_is_rejected(field: str):
    """A worker of the previous contract version must not be understood by halves."""
    data = CeremonyContextBuilder().build().model_dump(mode="json")
    del data[field]

    with pytest.raises(ValidationError):
        CeremonyContext.model_validate(data)


def test_the_round_starts_at_turn_one():
    with pytest.raises(ValidationError):
        ParticipantContextBuilder().in_turn(0).build()


def test_result_survives_a_json_round_trip_with_its_segments_and_events():
    """CA2: the attributed transcript and the ceremony events travel together."""
    diego = next_id()
    result = (
        CeremonyResultBuilder()
        .with_present(diego)
        .with_segments(TranscriptSegmentBuilder().said_by(diego).build())
        .with_events(
            CeremonyEventBuilder().build(),
            CeremonyEventBuilder().of_type(CeremonyEventType.TURN_STARTED).about(diego).build(),
            CeremonyEventBuilder().of_type(CeremonyEventType.TURN_ENDED).about(diego).build(),
            CeremonyEventBuilder()
            .of_type(CeremonyEventType.CEREMONY_CLOSED)
            .happened_at(CLOSED_AT)
            .build(),
        )
        .build()
    )

    restored = CeremonyResult.model_validate_json(result.model_dump_json())

    assert restored == result
    assert [event.type for event in restored.events] == [
        CeremonyEventType.CEREMONY_STARTED,
        CeremonyEventType.TURN_STARTED,
        CeremonyEventType.TURN_ENDED,
        CeremonyEventType.CEREMONY_CLOSED,
    ]


def test_a_result_without_events_is_rejected():
    """``events`` may be empty, but leaving it out is a worker of the previous version."""
    data = CeremonyResultBuilder().build().model_dump(mode="json")
    del data["events"]

    with pytest.raises(ValidationError):
        CeremonyResult.model_validate(data)


def test_result_allows_a_degraded_ceremony_without_segments():
    result = CeremonyResultBuilder().degraded("The transcription service did not respond").build()

    assert result.status is CeremonyStatus.DEGRADED
    assert result.degraded is True
    assert result.segments == []


def test_an_event_about_the_ceremony_itself_names_nobody():
    event = CeremonyEventBuilder().build()

    assert event.user_id is None
    assert event.model_dump(mode="json") == {
        "type": "ceremony_started",
        "at": STARTED_AT.isoformat().replace("+00:00", "Z"),
        "user_id": None,
    }


def test_an_event_type_outside_the_closed_list_is_rejected():
    data = CeremonyEventBuilder().build().model_dump(mode="json")
    data["type"] = "someone_sneezed"

    with pytest.raises(ValidationError):
        CeremonyEvent.model_validate(data)


def test_event_types_are_the_agreed_closed_list():
    assert {event_type.value for event_type in CeremonyEventType} == {
        "ceremony_started",
        "turn_started",
        "turn_ended",
        "degraded",
        "ceremony_closed",
    }


def test_the_receipt_only_says_received():
    assert ResultReceipt().model_dump(mode="json") == {"status": "received"}
    with pytest.raises(ValidationError):
        ResultReceipt.model_validate({"status": "rejected"})


def test_segment_keeps_speaker_and_timestamps():
    segment = TranscriptSegmentBuilder().build()

    assert segment.room_identity == str(segment.user_id)
    assert segment.end_ms > segment.start_ms


def test_enum_values_match_the_database_enum_types():
    """The values travel through the API and are stored as PostgreSQL enums."""
    assert {mode.value for mode in OperationMode} == {"support", "autonomous"}
    assert {role.value for role in TeamRole} == {"admin", "member"}
