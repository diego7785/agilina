"""The part of a LiveKit job the room job touches: connecting, the room name, the
agent's own attributes, waiting for the first person and the shutdown callbacks; and the
voice session the real synthesizer speaks through."""

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

from livekit.agents import (
    AgentStateChangedEvent,
    AutoSubscribe,
    CloseEvent,
    CloseReason,
    ErrorEvent,
    tts,
)


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
    """A sentence in the session. Unless ``hangs``, its playout is already over; a hanging
    one ends only when it is interrupted, and only by a forced interruption."""

    def __init__(self, *, hangs: bool = False) -> None:
        self.interrupted = False
        self.forced = False
        self._done = asyncio.Event()
        if not hangs:
            self._done.set()

    async def wait_for_playout(self) -> None:
        await self._done.wait()

    def interrupt(self, *, force: bool = False) -> "FakeSpeech":
        if not force:
            raise RuntimeError("This speech does not allow interruptions")
        self.interrupted = True
        self.forced = True
        self._done.set()
        return self


class FakeAgentSession:
    """Records how the voice session is started, what it says and whether it closes.

    Each sentence is heard at once (``agent_state_changed`` to ``speaking``), unless:
    ``tts_failure`` makes it fail as LiveKit reports it, an "error" event with the speech
    neither raised nor interrupted; ``silent`` makes it end without any audio; and
    ``hangs`` makes it never start until it is interrupted."""

    def __init__(
        self,
        tts_failure: Exception | None = None,
        *,
        silent: bool = False,
        hangs: bool = False,
    ) -> None:
        self.started: list[dict[str, Any]] = []
        self.said: list[str] = []
        self.speeches: list[FakeSpeech] = []
        self.closed = False
        self.handlers: dict[str, list[Callable[[Any], None]]] = {}
        self._tts_failure = tts_failure
        self._silent = silent
        self._hangs = hangs

    @property
    def error_handlers(self) -> list[Callable[[Any], None]]:
        return self.handlers.get("error", [])

    async def start(self, **options: Any) -> None:
        self.started.append(options)

    def on(self, event: str, handler: Callable[[Any], None]) -> None:
        self.handlers.setdefault(event, []).append(handler)

    def off(self, event: str, handler: Callable[[Any], None]) -> None:
        self.handlers[event].remove(handler)

    def emit(self, event: str, payload: Any) -> None:
        for handler in list(self.handlers.get(event, [])):
            handler(payload)

    def say(self, text: str) -> FakeSpeech:
        self.said.append(text)
        speech = FakeSpeech(hangs=self._hangs)
        self.speeches.append(speech)
        if self._tts_failure is not None:
            error = tts.TTSError(
                timestamp=0, label="elevenlabs", error=self._tts_failure, recoverable=False
            )
            self.emit("error", ErrorEvent(error=error, source=None))
        elif not self._silent and not self._hangs:
            self.emit(
                "agent_state_changed",
                AgentStateChangedEvent(old_state="listening", new_state="speaking"),
            )
        return speech

    def close_on_errors(self) -> None:
        """What AgentSession does after too many unrecoverable errors in a row."""
        self.emit("close", CloseEvent(error=None, reason=CloseReason.ERROR))

    async def aclose(self) -> None:
        self.closed = True
