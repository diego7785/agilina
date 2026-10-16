"""The Ceremony aggregate: one result per ceremony, spoken only by its participants (AGI-64,
AGI-126)."""

import pytest

from agilina_api.ceremonies.domain.errors import NotAParticipantError, ResultAlreadyReceivedError
from tests.api.builders import CeremonyBuilder, next_id

DIGEST = "a" * 64
OTHER_DIGEST = "b" * 64


def test_a_first_result_is_new_and_the_ceremony_keeps_its_digest():
    ana = next_id()
    ceremony = CeremonyBuilder().aggregate()

    assert ceremony.receive_result(DIGEST, {"segments.0.user_id": ana}, {ana}) is True
    assert ceremony.result_digest == DIGEST


def test_the_same_result_again_is_not_new_and_nothing_changes():
    ceremony = CeremonyBuilder().with_result_received(DIGEST).aggregate()

    assert ceremony.receive_result(DIGEST, {}, ()) is False
    assert ceremony.result_digest == DIGEST


def test_the_same_result_again_is_accepted_even_if_its_speaker_left_the_participants():
    """A retry of the worker must not fail because someone left the sprint since."""
    ceremony = CeremonyBuilder().with_result_received(DIGEST).aggregate()

    assert ceremony.receive_result(DIGEST, {"segments.0.user_id": next_id()}, ()) is False


def test_another_result_for_a_ceremony_that_has_one_is_refused():
    ceremony = CeremonyBuilder().with_result_received(DIGEST).aggregate()

    with pytest.raises(ResultAlreadyReceivedError):
        ceremony.receive_result(OTHER_DIGEST, {}, ())

    assert ceremony.result_digest == DIGEST


def test_a_result_with_someone_who_is_not_a_participant_names_where_and_never_who():
    ana, stranger, intruder = next_id(), next_id(), next_id()
    ceremony = CeremonyBuilder().aggregate()
    speakers = {
        "segments.0.user_id": ana,
        "segments.1.user_id": stranger,
        "events.2.user_id": intruder,
    }

    with pytest.raises(NotAParticipantError) as raised:
        ceremony.receive_result(DIGEST, speakers, {ana})

    assert raised.value.fields == ("segments.1.user_id", "events.2.user_id")
    assert str(stranger) not in str(raised.value) and str(intruder) not in str(raised.value)
    assert ceremony.result_digest is None


def test_a_result_where_nobody_spoke_is_new():
    ceremony = CeremonyBuilder().aggregate()

    assert ceremony.receive_result(DIGEST, {}, ()) is True


def test_the_ceremony_knows_its_team_sprint_and_instant():
    builder = CeremonyBuilder()
    ceremony = builder.aggregate()

    assert ceremony.id == builder.ceremony_id
    assert (ceremony.team_id, ceremony.sprint_id) == (builder.team_id, builder.sprint_id)
    assert ceremony.scheduled_at == builder.scheduled_at
