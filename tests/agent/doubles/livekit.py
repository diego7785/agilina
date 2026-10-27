"""The part of a LiveKit job the room job touches: connecting, the room name, the
agent's own attributes, waiting for the first person and the shutdown callbacks; and the
voice session the real synthesizer speaks through."""

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

from livekit.agents import AutoSubscribe, ErrorEvent, tts


@dataclass
class FakeLocalParticipant:
    attributes: dict[str, str] = field(default_factory=dict)

    async def set_attributes(self, attributes: dict[str, str]) -> None:
        self.attributes.update(attributes)


@dataclass
class FakeRoom:
    name: str
    local_participant: FakeLocalParticipant = field(default_factory=FakeLocalParticipant)


class FakeJobContext:
    """By default someone is already in the room; with ``nobody_yet`` the wait blocks
    until ``person_joins``. With ``connect_failure`` joining the room raises it."""

    def __init__(
        self,
        room_name: str,
        *,
        nobody_yet: bool = False,
        connect_failure: Exception | None = None,
    ) -> None:
        self.room = FakeRoom(room_name)
        self._connect_failure = connect_failure
        self.subscribed: AutoSubscribe | None = None
        self.waited_for_participant = 0
        self._someone_joined = asyncio.Event()
        if not nobody_yet:
            self._someone_joined.set()
        self.shutdown_callbacks: list[Callable[..., Coroutine[Any, Any, None]]] = []

    async def connect(self, auto_subscribe: AutoSubscribe = AutoSubscribe.SUBSCRIBE_ALL) -> None:
        if self._connect_failure is not None:
            raise self._connect_failure
        self.subscribed = auto_subscribe

    async def wait_for_participant(self) -> None:
        self.waited_for_participant += 1
        await self._someone_joined.wait()

    def person_joins(self) -> None:
        self._someone_joined.set()

    def add_shutdown_callback(self, callback: Callable[..., Coroutine[Any, Any, None]]) -> None:
        self.shutdown_callbacks.append(callback)


class FakeSpeech:
    interrupted = False

    async def wait_for_playout(self) -> None:
        return None


class FakeAgentSession:
    """Records how the voice session is started, what it says and whether it closes.
    With ``tts_failure`` each sentence fails as LiveKit reports it: an "error" event once
    the TTS retries run out, with the speech neither raised nor interrupted."""

    def __init__(self, tts_failure: Exception | None = None) -> None:
        self.started: list[dict[str, Any]] = []
        self.said: list[str] = []
        self.closed = False
        self.error_handlers: list[Callable[[ErrorEvent], None]] = []
        self._tts_failure = tts_failure

    async def start(self, **options: Any) -> None:
        self.started.append(options)

    def on(self, event: str, handler: Callable[[ErrorEvent], None]) -> None:
        assert event == "error"
        self.error_handlers.append(handler)

    def off(self, event: str, handler: Callable[[ErrorEvent], None]) -> None:
        assert event == "error"
        self.error_handlers.remove(handler)

    def say(self, text: str) -> FakeSpeech:
        self.said.append(text)
        if self._tts_failure is not None:
            error = tts.TTSError(
                timestamp=0, label="elevenlabs", error=self._tts_failure, recoverable=False
            )
            for handler in list(self.error_handlers):
                handler(ErrorEvent(error=error, source=None))
        return FakeSpeech()

    async def aclose(self) -> None:
        self.closed = True
