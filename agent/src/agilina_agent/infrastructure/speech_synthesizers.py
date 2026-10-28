"""Speech synthesis adapters.

The real voice speaks through a LiveKit ``AgentSession`` that only talks: no STT, no
VAD, no reading of the room audio, end of turn detection set to manual and
interruptions off. Without that explicit configuration livekit-agents turns on by
itself, in dev mode, the cloud turn-detector-v1 and the AdaptiveInterruptionDetector,
which send the people's audio to LiveKit's services (CA8). The session is never
recorded, and ElevenLabs only receives the text of the template, never room audio.

A sentence that is not heard within five seconds, or that ElevenLabs rejects, raises
``SpeechUnavailableError`` so the room shows it as text (AGI-69). The log keeps how long
each sentence took to be heard and how many characters it spent from the monthly quota.

The recording synthesizer lets the whole ceremony run locally, and in the tests,
without spending minutes of a paid service.
"""

import asyncio
import time
from collections.abc import Callable
from typing import Any, NoReturn

from livekit import rtc
from livekit.agents import (
    Agent,
    AgentSession,
    AgentStateChangedEvent,
    APIConnectOptions,
    APIStatusError,
    APITimeoutError,
    CloseEvent,
    ErrorEvent,
    TurnHandlingOptions,
    tts,
)
from livekit.agents.metrics import TTSMetrics
from livekit.agents.voice import SpeechHandle
from livekit.agents.voice.agent_session import SessionConnectOptions
from livekit.agents.voice.room_io import RoomOptions
from livekit.plugins import elevenlabs

from agilina_agent.application.errors import SpeechFailure, SpeechUnavailableError
from agilina_agent.application.ports import SpeechSynthesizer
from agilina_agent.infrastructure.logging_setup import get_logger
from agilina_shared.enums import Language

logger = get_logger(__name__)

TURN_HANDLING: TurnHandlingOptions = {
    "turn_detection": "manual",
    "interruption": {"enabled": False},
}
# Agilina speaks into the room but does not take its audio or its text chat, and
# publishes no transcript (its token has no data channel). The session does not close
# when a person leaves: the job owns the life cycle.
ROOM_OPTIONS = RoomOptions(
    audio_input=False, text_input=False, text_output=False, close_on_disconnect=False
)
RECORD = False
# No RemoteSession may observe or drive the session over the room.
SESSION_HOST = False

# A sentence not heard by then is shown as text: the ceremony does not wait for the voice.
SPEECH_START_TIMEOUT = 5.0
# Above this the voice no longer feels like part of the conversation (CA3).
TARGET_LATENCY = 2.0
# No retries: the plugin's default (3 retries of 10 s) would keep the room waiting ~40 s.
TTS_CONNECTION = APIConnectOptions(max_retry=0, timeout=SPEECH_START_TIMEOUT)
# eleven_v4_turbo and eleven_flash_v2_5 charge half a credit per character (HU-01 spike).
CREDITS_PER_CHARACTER = 0.5
# The websocket of the dialogue models reports these without an HTTP status.
QUOTA_MARKERS = ("quota_exceeded", "too_many_concurrent_requests", "rate_limit")


def new_session(voice: tts.TTS[Any]) -> AgentSession[None]:
    """A session that only speaks: no STT, no VAD and no cloud detectors."""
    return AgentSession(
        tts=voice,
        vad=None,
        turn_handling=TURN_HANDLING,
        conn_options=SessionConnectOptions(tts_conn_options=TTS_CONNECTION),
    )


def failure_of(error: Exception) -> SpeechFailure:
    """What ElevenLabs answered, as far as the room is concerned."""
    if isinstance(error, APIStatusError):
        if error.status_code == 401:
            return SpeechFailure.INVALID_KEY
        if error.status_code == 429:
            return SpeechFailure.QUOTA_OR_RATE_LIMIT
        return SpeechFailure.PROVIDER_ERROR
    if isinstance(error, APITimeoutError):
        return SpeechFailure.TIMEOUT
    if any(marker in str(error) for marker in QUOTA_MARKERS):
        return SpeechFailure.QUOTA_OR_RATE_LIMIT
    return SpeechFailure.PROVIDER_ERROR


def credits_for(characters: int) -> str:
    return f"{characters * CREDITS_PER_CHARACTER:g}"


class ElevenLabsSynthesizer(SpeechSynthesizer):
    """Says the text in the room with ElevenLabs. The audio goes straight into the room.
    The session starts on the first sentence and is replaced if it closes on errors."""

    def __init__(
        self,
        room: rtc.Room,
        api_key: str,
        model: str,
        voice_by_language: dict[Language, str],
        *,
        start_timeout: float = SPEECH_START_TIMEOUT,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._room = room
        self._voice_by_language = voice_by_language
        self._start_timeout = start_timeout
        self._clock = clock
        self._tts = elevenlabs.TTS(api_key=api_key, model=model)
        self._tts.on("metrics_collected", self._count)
        self._session: AgentSession[None] | None = None
        self._characters = 0

    async def synthesize(self, text: str, language: Language) -> None:
        # An empty voice falls back to the plugin's default one, not to the last used. The
        # language makes the model pronounce and normalize the text in it (CA2).
        voice_id = self._voice_by_language.get(language) or elevenlabs.DEFAULT_VOICE_ID
        self._tts.update_options(voice_id=voice_id, language=language.value)
        session = await self._running_session()

        # A TTS failure stays inside the session: it is not raised and the speech is not
        # marked interrupted, it only shows up as an "error" event.
        failures: list[Exception] = []
        heard = asyncio.Event()
        heard_at: list[float] = []

        def on_error(event: ErrorEvent) -> None:
            if isinstance(event.error, tts.TTSError) and not event.error.recoverable:
                failures.append(event.error.error)

        def on_state(event: AgentStateChangedEvent) -> None:
            # The first audio frame is in the room's track: from here on it is heard.
            if event.new_state == "speaking" and not heard.is_set():
                heard_at.append(self._clock())
                heard.set()

        session.on("error", on_error)
        session.on("agent_state_changed", on_state)
        decided_at = self._clock()
        try:
            speech = session.say(text)
            timed_out = not await self._heard_in_time(speech, heard)
            await speech.wait_for_playout()
        finally:
            session.off("error", on_error)
            session.off("agent_state_changed", on_state)

        if failures:
            self._fail(failure_of(failures[0]), language, failures[0])
        if not heard_at:
            reason = SpeechFailure.TIMEOUT if timed_out else SpeechFailure.PROVIDER_ERROR
            self._fail(reason, language, "no audio")
        self._log_latency(heard_at[0] - decided_at, language)

    async def close(self) -> None:
        if self._session is not None:
            await self._session.aclose()
        # The session does not close the TTS it was given: its websocket is ours.
        await self._tts.aclose()
        if self._characters:
            logger.info(
                "ElevenLabs used %d characters (≈ %s credits) in room %s",
                self._characters,
                credits_for(self._characters),
                self._room.name,
            )

    async def _running_session(self) -> AgentSession[None]:
        if self._session is not None:
            return self._session
        session = new_session(self._tts)

        def forget(_event: CloseEvent) -> None:
            # Four TTS failures in a row close the session: the next sentence opens another.
            if self._session is session:
                self._session = None

        session.on("close", forget)
        await session.start(
            agent=Agent(instructions=""),
            room=self._room,
            room_options=ROOM_OPTIONS,
            record=RECORD,
            session_host=SESSION_HOST,
        )
        # Kept only once started, so a failed start is retried on the next sentence.
        self._session = session
        return session

    async def _heard_in_time(self, speech: SpeechHandle, heard: asyncio.Event) -> bool:
        """Waits until the first audio is in the room or the speech ends, at most the start
        timeout. Past it the speech is cut, so it does not sound late over the text."""
        playout = asyncio.ensure_future(speech.wait_for_playout())
        speaking = asyncio.ensure_future(heard.wait())
        try:
            done, _ = await asyncio.wait(
                {playout, speaking},
                timeout=self._start_timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            playout.cancel()
            speaking.cancel()
        if not done:
            # Interruptions are off in this session (AD-32): only a forced one cuts it.
            speech.interrupt(force=True)
        return bool(done)

    def _fail(self, reason: SpeechFailure, language: Language, detail: object) -> NoReturn:
        if reason is SpeechFailure.INVALID_KEY:
            logger.error("ElevenLabs rejected the API key in room %s: %s", self._room.name, detail)
        elif reason is SpeechFailure.QUOTA_OR_RATE_LIMIT:
            logger.warning(
                "ElevenLabs quota or rate limit in room %s (%s) after %d characters (≈ %s "
                "credits) in this room: %s",
                self._room.name,
                language.value,
                self._characters,
                credits_for(self._characters),
                detail,
            )
        else:
            logger.warning(
                "ElevenLabs did not speak in room %s (%s, %s): %s",
                self._room.name,
                language.value,
                reason.value,
                detail,
            )
        raise SpeechUnavailableError(reason)

    def _log_latency(self, latency: float, language: Language) -> None:
        log = logger.warning if latency > TARGET_LATENCY else logger.info
        log(
            "ElevenLabs started speaking in %d ms in room %s (%s)",
            round(latency * 1000),
            self._room.name,
            language.value,
        )

    def _count(self, metrics: TTSMetrics) -> None:
        self._characters += metrics.characters_count
        logger.info(
            "ElevenLabs spoke %d characters (≈ %s credits), first audio from ElevenLabs in %d ms",
            metrics.characters_count,
            credits_for(metrics.characters_count),
            round(metrics.ttfb * 1000),
        )


class RecordingSynthesizer(SpeechSynthesizer):
    """Records what Agilina would say instead of synthesizing it.

    It is what lets a ceremony run end to end locally, and also what the tests
    use.
    """

    def __init__(self) -> None:
        self.spoken: list[tuple[Language, str]] = []

    async def synthesize(self, text: str, language: Language) -> None:
        self.spoken.append((language, text))
        logger.info("[simulated voice · %s] %s", language.value, text)
