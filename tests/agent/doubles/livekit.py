"""The part of a LiveKit job the room job touches: connecting, the room name, the
agent's own attributes, waiting for the first person and the shutdown callbacks."""

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

from livekit.agents import AutoSubscribe


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
    until ``person_joins``."""

    def __init__(self, room_name: str, *, nobody_yet: bool = False) -> None:
        self.room = FakeRoom(room_name)
        self.subscribed: AutoSubscribe | None = None
        self.waited_for_participant = 0
        self._someone_joined = asyncio.Event()
        if not nobody_yet:
            self._someone_joined.set()
        self.shutdown_callbacks: list[Callable[..., Coroutine[Any, Any, None]]] = []

    async def connect(self, auto_subscribe: AutoSubscribe = AutoSubscribe.SUBSCRIBE_ALL) -> None:
        self.subscribed = auto_subscribe

    async def wait_for_participant(self) -> None:
        self.waited_for_participant += 1
        await self._someone_joined.wait()

    def person_joins(self) -> None:
        self._someone_joined.set()

    def add_shutdown_callback(self, callback: Callable[..., Coroutine[Any, Any, None]]) -> None:
        self.shutdown_callbacks.append(callback)
