"""Speech synthesis adapters.

The real voice speaks through a LiveKit ``AgentSession`` that only talks: no STT, no
VAD, no reading of the room audio, end of turn detection set to manual and
interruptions off. Without that explicit configuration livekit-agents turns on by
itself, in dev mode, the cloud turn-detector-v1 and the AdaptiveInterruptionDetector,
which send the people's audio to LiveKit's services (CA8). The session is never
recorded, and ElevenLabs only receives the text of the template, never room audio.

The recording synthesizer lets the whole ceremony run locally, and in the tests,
without spending minutes of a paid service.
"""

from typing import Any

from livekit import rtc
from livekit.agents import Agent, AgentSession, ErrorEvent, TurnHandlingOptions, tts
from livekit.agents.voice.room_io import RoomOptions
from livekit.plugins import elevenlabs

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


def new_session(voice: tts.TTS[Any]) -> AgentSession[None]:
    """A session that only speaks: no STT, no VAD and no cloud detectors."""
    return AgentSession(tts=voice, vad=None, turn_handling=TURN_HANDLING)


class ElevenLabsSynthesizer(SpeechSynthesizer):
    """Says the text in the room with ElevenLabs. The audio goes straight into the room,
    so it returns no bytes. The session starts on the first sentence."""

    def __init__(
        self, room: rtc.Room, api_key: str, voice_by_language: dict[Language, str]
    ) -> None:
        self._room = room
        self._voice_by_language = voice_by_language
        self._tts = elevenlabs.TTS(api_key=api_key)
        self._session: AgentSession[None] | None = None

    async def synthesize(self, text: str, language: Language) -> bytes:
        # An empty voice falls back to the plugin's default one, not to the last used.
        voice_id = self._voice_by_language.get(language) or elevenlabs.DEFAULT_VOICE_ID
        self._tts.update_options(voice_id=voice_id)
        if self._session is None:
            session = new_session(self._tts)
            await session.start(
                agent=Agent(instructions=""),
                room=self._room,
                room_options=ROOM_OPTIONS,
                record=RECORD,
                session_host=SESSION_HOST,
            )
            # Kept only once started, so a failed start is retried on the next sentence.
            self._session = session
        # A TTS failure stays inside the session: it is not raised and the speech is not
        # marked interrupted, it only shows up as an "error" event once the retries run out.
        failures: list[tts.TTSError] = []

        def on_error(event: ErrorEvent) -> None:
            if isinstance(event.error, tts.TTSError) and not event.error.recoverable:
                failures.append(event.error)

        self._session.on("error", on_error)
        try:
            speech = self._session.say(text)
            await speech.wait_for_playout()
        finally:
            self._session.off("error", on_error)
        if failures or speech.interrupted:
            reason = failures[0].error if failures else "interrupted"
            logger.warning(
                "ElevenLabs did not speak in room %s (%s): %s",
                self._room.name,
                language.value,
                reason,
            )
        else:
            logger.info("ElevenLabs spoke %d characters in %s", len(text), language.value)
        return b""

    async def close(self) -> None:
        if self._session is not None:
            await self._session.aclose()
        # The session does not close the TTS it was given: its websocket is ours.
        await self._tts.aclose()


class RecordingSynthesizer(SpeechSynthesizer):
    """Records what Agilina would say instead of synthesizing it.

    It is what lets a ceremony run end to end locally, and also what the tests
    use.
    """

    def __init__(self) -> None:
        self.spoken: list[tuple[Language, str]] = []

    async def synthesize(self, text: str, language: Language) -> bytes:
        self.spoken.append((language, text))
        logger.info("[simulated voice · %s] %s", language.value, text)
        return b""
