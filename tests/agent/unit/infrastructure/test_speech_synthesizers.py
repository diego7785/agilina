"""The real voice speaks through a session that sends no audio to LiveKit's cloud
detectors, does not take the room audio and is never recorded (CA6, CA8 of AGI-62). It
speaks with eleven_v4_turbo in the team language, gives up after five seconds without
audio, tells the room why it did not speak and logs latency and consumption (AGI-69)."""

from collections.abc import Callable, Iterator

import pytest
from livekit.agents import APIError, APIStatusError, APITimeoutError
from livekit.agents.metrics import TTSMetrics
from livekit.plugins import elevenlabs

from agilina_agent.application.errors import SpeechFailure, SpeechUnavailableError
from agilina_agent.infrastructure import speech_synthesizers
from agilina_agent.infrastructure.speech_synthesizers import (
    RECORD,
    ROOM_OPTIONS,
    SESSION_HOST,
    SPEECH_START_TIMEOUT,
    TURN_HANDLING,
    ElevenLabsSynthesizer,
    failure_of,
    new_session,
)
from agilina_shared.enums import Language
from tests.agent.doubles.livekit import FakeAgentSession, FakeRoom

MODEL = "eleven_v4_turbo"


class FakeTTS:
    """Records how it was created and the voice and language set before each sentence."""

    def __init__(self, **options: object) -> None:
        self.options = options
        self.updates: list[dict[str, str]] = []
        self.listeners: dict[str, Callable[[TTSMetrics], None]] = {}
        self.closed = False

    def on(self, event: str, callback: Callable[[TTSMetrics], None]) -> None:
        self.listeners[event] = callback

    def update_options(self, *, voice_id: str, language: str) -> None:
        self.updates.append({"voice_id": voice_id, "language": language})

    async def aclose(self) -> None:
        self.closed = True


def _synthesizer(
    session: FakeAgentSession | list[FakeAgentSession] | None = None,
    *,
    monkeypatch: pytest.MonkeyPatch,
    voices: dict[Language, str] | None = None,
    start_timeout: float = SPEECH_START_TIMEOUT,
    clock: Callable[[], float] | None = None,
) -> ElevenLabsSynthesizer:
    sessions = iter(session if isinstance(session, list) else [session or FakeAgentSession()])
    monkeypatch.setattr(speech_synthesizers.elevenlabs, "TTS", FakeTTS)
    monkeypatch.setattr(speech_synthesizers, "new_session", lambda _voice: next(sessions))
    extra = {} if clock is None else {"clock": clock}
    return ElevenLabsSynthesizer(
        FakeRoom("acme-room"),  # type: ignore[arg-type]
        api_key="test-key",
        model=MODEL,
        voice_by_language=voices if voices is not None else {Language.ES: "voice-es"},
        start_timeout=start_timeout,
        **extra,  # type: ignore[arg-type]
    )


def _metrics(characters: int, ttfb: float = 0.5) -> TTSMetrics:
    return TTSMetrics(
        label="elevenlabs",
        request_id="request-1",
        timestamp=0,
        ttfb=ttfb,
        duration=1.0,
        audio_duration=2.0,
        cancelled=False,
        characters_count=characters,
        streamed=True,
    )


def _ticking(*readings: float) -> Callable[[], float]:
    values: Iterator[float] = iter(readings)
    return lambda: next(values)


# ------------------------------------------------------------- the session (AD-32) --
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


async def test_the_session_does_not_retry_the_voice_for_longer_than_the_room_waits() -> None:
    session = new_session(elevenlabs.TTS(api_key="test-key"))

    assert session.conn_options.tts_conn_options.max_retry == 0
    assert session.conn_options.tts_conn_options.timeout == SPEECH_START_TIMEOUT == 5.0


def test_the_session_does_not_take_the_room_audio() -> None:
    assert ROOM_OPTIONS.audio_input is False
    assert ROOM_OPTIONS.text_input is False
    # Its token has no data channel: no transcript is published either.
    assert ROOM_OPTIONS.text_output is False


async def test_the_session_starts_once_unrecorded_and_says_each_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeAgentSession()
    synthesizer = _synthesizer(
        session, monkeypatch=monkeypatch, voices={Language.ES: "voice-es", Language.EN: ""}
    )

    await synthesizer.synthesize("Hola", Language.ES)
    await synthesizer.synthesize("Hello", Language.EN)
    await synthesizer.close()

    [options] = session.started
    assert RECORD is False
    assert options["record"] is RECORD
    assert options["room"] is synthesizer._room
    assert options["room_options"] is ROOM_OPTIONS
    assert SESSION_HOST is False
    assert options["session_host"] is SESSION_HOST
    assert session.said == ["Hola", "Hello"]
    assert session.closed
    assert synthesizer._tts.closed  # type: ignore[attr-defined]


async def test_closing_before_speaking_does_nothing() -> None:
    synthesizer = ElevenLabsSynthesizer(
        FakeRoom("acme-room"),  # type: ignore[arg-type]
        api_key="test-key",
        model=MODEL,
        voice_by_language={},
    )

    await synthesizer.close()


async def test_each_sentence_leaves_no_listener_behind(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeAgentSession()
    synthesizer = _synthesizer(session, monkeypatch=monkeypatch)

    await synthesizer.synthesize("Hola", Language.ES)

    assert session.handlers["error"] == []
    assert session.handlers["agent_state_changed"] == []


# ----------------------------------------------------------- model and language --
def test_the_voice_uses_the_configured_model() -> None:
    synthesizer = ElevenLabsSynthesizer(
        FakeRoom("acme-room"),  # type: ignore[arg-type]
        api_key="test-key",
        model=MODEL,
        voice_by_language={},
    )

    assert synthesizer._tts.model == "eleven_v4_turbo"


async def test_each_language_speaks_with_its_voice_or_the_default_one_and_its_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    synthesizer = _synthesizer(
        monkeypatch=monkeypatch, voices={Language.ES: "voice-es", Language.EN: ""}
    )

    await synthesizer.synthesize("Hola", Language.ES)
    await synthesizer.synthesize("Hello", Language.EN)
    await synthesizer.synthesize("Hola otra vez", Language.ES)

    assert synthesizer._tts.options["model"] == MODEL  # type: ignore[attr-defined]
    assert synthesizer._tts.updates == [  # type: ignore[attr-defined]
        {"voice_id": "voice-es", "language": "es"},
        {"voice_id": elevenlabs.DEFAULT_VOICE_ID, "language": "en"},
        {"voice_id": "voice-es", "language": "es"},
    ]


# ------------------------------------------------------------- failures (CA4) --
@pytest.mark.parametrize(
    ("error", "failure"),
    [
        (APIStatusError("unauthorized", status_code=401), SpeechFailure.INVALID_KEY),
        (APIStatusError("too many", status_code=429), SpeechFailure.QUOTA_OR_RATE_LIMIT),
        (APIStatusError("unavailable", status_code=503), SpeechFailure.PROVIDER_ERROR),
        (APIStatusError("payment", status_code=402), SpeechFailure.PROVIDER_ERROR),
        (APIError("quota_exceeded: no credits left"), SpeechFailure.QUOTA_OR_RATE_LIMIT),
        (APIError("too_many_concurrent_requests"), SpeechFailure.QUOTA_OR_RATE_LIMIT),
        (APIError("something else"), SpeechFailure.PROVIDER_ERROR),
        (APITimeoutError(), SpeechFailure.TIMEOUT),
        (Exception("paid_plan_required"), SpeechFailure.PROVIDER_ERROR),
    ],
)
def test_each_answer_of_elevenlabs_is_a_known_failure(
    error: Exception, failure: SpeechFailure
) -> None:
    assert failure_of(error) is failure


async def test_a_rejected_key_is_an_alert_and_the_sentence_is_not_heard(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    session = FakeAgentSession(tts_failure=APIStatusError("invalid_api_key", status_code=401))
    synthesizer = _synthesizer(session, monkeypatch=monkeypatch)

    with pytest.raises(SpeechUnavailableError) as raised:
        await synthesizer.synthesize("Hola", Language.ES)

    assert raised.value.reason is SpeechFailure.INVALID_KEY
    [record] = [r for r in caplog.records if "ElevenLabs" in r.getMessage()]
    assert record.levelname == "ERROR"
    assert "ElevenLabs rejected the API key in room acme-room" in record.getMessage()
    assert "test-key" not in caplog.text
    assert session.error_handlers == []


async def test_an_exhausted_quota_logs_what_the_room_spent(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    session = FakeAgentSession(tts_failure=APIStatusError("quota", status_code=429))
    synthesizer = _synthesizer(session, monkeypatch=monkeypatch)
    synthesizer._tts.listeners["metrics_collected"](_metrics(90))  # type: ignore[attr-defined]

    with pytest.raises(SpeechUnavailableError) as raised:
        await synthesizer.synthesize("Hola", Language.ES)

    assert raised.value.reason is SpeechFailure.QUOTA_OR_RATE_LIMIT
    assert (
        "ElevenLabs quota or rate limit in room acme-room (es) after 90 characters "
        "(≈ 45 credits) in this room" in caplog.text
    )


async def test_a_provider_error_is_logged_as_not_spoken(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    session = FakeAgentSession(tts_failure=Exception("paid_plan_required"))
    synthesizer = _synthesizer(session, monkeypatch=monkeypatch)

    with pytest.raises(SpeechUnavailableError) as raised:
        await synthesizer.synthesize("Hola", Language.ES)

    assert raised.value.reason is SpeechFailure.PROVIDER_ERROR
    assert (
        "ElevenLabs did not speak in room acme-room (es, provider_error): paid_plan_required"
        in caplog.text
    )
    assert "started speaking" not in caplog.text


async def test_a_voice_that_does_not_start_in_time_is_cut_and_not_heard(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    session = FakeAgentSession(hangs=True)
    synthesizer = _synthesizer(session, monkeypatch=monkeypatch, start_timeout=0.01)

    with pytest.raises(SpeechUnavailableError) as raised:
        await synthesizer.synthesize("Hola", Language.ES)

    assert raised.value.reason is SpeechFailure.TIMEOUT
    [speech] = session.speeches
    # Interruptions are off in the session: only a forced one stops the late sentence.
    assert speech.forced
    assert "ElevenLabs did not speak in room acme-room (es, timeout): no audio" in caplog.text


async def test_a_sentence_that_ends_without_audio_is_not_heard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    synthesizer = _synthesizer(FakeAgentSession(silent=True), monkeypatch=monkeypatch)

    with pytest.raises(SpeechUnavailableError) as raised:
        await synthesizer.synthesize("Hola", Language.ES)

    assert raised.value.reason is SpeechFailure.PROVIDER_ERROR


async def test_a_session_closed_by_errors_is_replaced_on_the_next_sentence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken, replacement = FakeAgentSession(), FakeAgentSession()
    synthesizer = _synthesizer([broken, replacement], monkeypatch=monkeypatch)
    await synthesizer.synthesize("Hola", Language.ES)

    broken.close_on_errors()
    await synthesizer.synthesize("Hola otra vez", Language.ES)

    assert broken.said == ["Hola"]
    assert replacement.said == ["Hola otra vez"]
    assert len(replacement.started) == 1


async def test_closing_an_old_session_does_not_drop_the_current_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken, replacement = FakeAgentSession(), FakeAgentSession()
    synthesizer = _synthesizer([broken, replacement], monkeypatch=monkeypatch)
    await synthesizer.synthesize("Hola", Language.ES)
    broken.close_on_errors()
    await synthesizer.synthesize("Hola otra vez", Language.ES)

    broken.close_on_errors()
    await synthesizer.synthesize("Y otra", Language.ES)

    assert replacement.said == ["Hola otra vez", "Y otra"]


# ------------------------------------------------- latency (CA3) and consumption --
async def test_the_time_until_the_voice_is_heard_is_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    synthesizer = _synthesizer(monkeypatch=monkeypatch, clock=_ticking(1000.0, 1000.6))

    await synthesizer.synthesize("Hola", Language.ES)

    [record] = [r for r in caplog.records if "started speaking" in r.getMessage()]
    assert record.levelname == "INFO"
    assert record.getMessage() == "ElevenLabs started speaking in 600 ms in room acme-room (es)"


async def test_a_voice_heard_after_two_seconds_is_a_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    synthesizer = _synthesizer(monkeypatch=monkeypatch, clock=_ticking(1000.0, 1002.5))

    await synthesizer.synthesize("Hola", Language.ES)

    [record] = [r for r in caplog.records if "started speaking" in r.getMessage()]
    assert record.levelname == "WARNING"
    assert "2500 ms" in record.getMessage()


async def test_each_sentence_logs_its_characters_and_credits_and_the_room_its_total(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    synthesizer = _synthesizer(monkeypatch=monkeypatch)
    count = synthesizer._tts.listeners["metrics_collected"]  # type: ignore[attr-defined]

    count(_metrics(45, ttfb=0.48))
    count(_metrics(270))
    await synthesizer.close()

    assert (
        "ElevenLabs spoke 45 characters (≈ 22.5 credits), first audio from ElevenLabs in 480 ms"
        in caplog.text
    )
    assert "ElevenLabs used 315 characters (≈ 157.5 credits) in room acme-room" in caplog.text


async def test_a_room_that_spent_nothing_logs_no_total(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    synthesizer = _synthesizer(monkeypatch=monkeypatch)

    await synthesizer.close()

    assert "ElevenLabs used" not in caplog.text
