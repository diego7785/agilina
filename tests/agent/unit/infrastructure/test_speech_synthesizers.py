"""The real voice speaks through a session that sends no audio to LiveKit's cloud
detectors, does not take the room audio and is never recorded (CA6, CA8)."""

import pytest
from livekit.plugins import elevenlabs

from agilina_agent.infrastructure import speech_synthesizers
from agilina_agent.infrastructure.speech_synthesizers import (
    RECORD,
    ROOM_OPTIONS,
    SESSION_HOST,
    TURN_HANDLING,
    ElevenLabsSynthesizer,
    new_session,
)
from agilina_shared.enums import Language
from tests.agent.doubles.livekit import FakeAgentSession, FakeRoom


class FakeTTS:
    """Records the voice set before each sentence."""

    def __init__(self, **_options: object) -> None:
        self.voices: list[str] = []

    def update_options(self, *, voice_id: str) -> None:
        self.voices.append(voice_id)


def test_the_session_turns_off_the_cloud_end_of_turn_detector() -> None:
    assert TURN_HANDLING["turn_detection"] == "manual"


def test_the_session_turns_off_interruption_detection() -> None:
    assert TURN_HANDLING["interruption"] == {"enabled": False}


async def test_the_session_neither_listens_nor_detects_voice() -> None:
    session = new_session(elevenlabs.TTS(api_key="test-key"))

    assert session.stt is None
    assert session.vad is None
    assert session.turn_detection == "manual"
    assert session.options.interruption["enabled"] is False


def test_the_session_does_not_take_the_room_audio() -> None:
    assert ROOM_OPTIONS.audio_input is False
    assert ROOM_OPTIONS.text_input is False
    # Its token has no data channel: no transcript is published either.
    assert ROOM_OPTIONS.text_output is False


async def test_the_session_starts_once_unrecorded_and_says_each_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeAgentSession()
    monkeypatch.setattr(speech_synthesizers, "new_session", lambda _voice: session)
    room = FakeRoom("acme-room")
    synthesizer = ElevenLabsSynthesizer(
        room,  # type: ignore[arg-type]
        api_key="test-key",
        voice_by_language={Language.ES: "voice-es", Language.EN: ""},
    )

    assert await synthesizer.synthesize("Hola", Language.ES) == b""
    await synthesizer.synthesize("Hello", Language.EN)
    await synthesizer.close()

    [options] = session.started
    assert RECORD is False
    assert options["record"] is RECORD
    assert options["room"] is room
    assert options["room_options"] is ROOM_OPTIONS
    assert SESSION_HOST is False
    assert options["session_host"] is SESSION_HOST
    assert session.said == ["Hola", "Hello"]
    assert session.closed


async def test_closing_before_speaking_does_nothing() -> None:
    synthesizer = ElevenLabsSynthesizer(
        FakeRoom("acme-room"),  # type: ignore[arg-type]
        api_key="test-key",
        voice_by_language={},
    )

    await synthesizer.close()


async def test_each_language_speaks_with_its_voice_or_the_default_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(speech_synthesizers.elevenlabs, "TTS", FakeTTS)
    monkeypatch.setattr(speech_synthesizers, "new_session", lambda _voice: FakeAgentSession())
    synthesizer = ElevenLabsSynthesizer(
        FakeRoom("acme-room"),  # type: ignore[arg-type]
        api_key="test-key",
        voice_by_language={Language.ES: "voice-es", Language.EN: ""},
    )

    await synthesizer.synthesize("Hola", Language.ES)
    await synthesizer.synthesize("Hello", Language.EN)

    assert synthesizer._tts.voices == ["voice-es", elevenlabs.DEFAULT_VOICE_ID]  # type: ignore[attr-defined]
