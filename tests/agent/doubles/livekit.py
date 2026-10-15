"""The part of a LiveKit job the room job touches: connecting and the room name."""

from dataclasses import dataclass

from livekit.agents import AutoSubscribe


@dataclass
class FakeRoom:
    name: str


class FakeJobContext:
    def __init__(self, room_name: str) -> None:
        self.room = FakeRoom(room_name)
        self.subscribed: AutoSubscribe | None = None

    async def connect(self, auto_subscribe: AutoSubscribe = AutoSubscribe.SUBSCRIBE_ALL) -> None:
        self.subscribed = auto_subscribe
