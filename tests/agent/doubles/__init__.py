"""Doubles of the worker: the API, Keycloak, LiveKit and time, all in memory."""

from tests.agent.doubles.agilina_api import FakeAgilinaApi, ScriptedApi
from tests.agent.doubles.keycloak import FakeTokenEndpoint, FakeWorkerTokens
from tests.agent.doubles.livekit import FakeJobContext
from tests.agent.doubles.time import FakeMonotonicClock, RecordedSleep

__all__ = [
    "FakeAgilinaApi",
    "FakeJobContext",
    "FakeMonotonicClock",
    "FakeTokenEndpoint",
    "FakeWorkerTokens",
    "RecordedSleep",
    "ScriptedApi",
]
